"""Rules service - deterministic rules engine (trigger + match + ordered actions)."""

from __future__ import annotations

import json
import logging
import re
import signal
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aiogram.types import Message
from sqlalchemy import select

from database.db import db
from database.models import Rule, RuleAction, RuleWarning

logger = logging.getLogger(__name__)

# ============================================================================
# REGEX SAFETY - Protection against ReDoS attacks
# ============================================================================

# Maximum allowed regex pattern length
MAX_REGEX_LENGTH = 500

# Patterns that indicate potential ReDoS vulnerability (nested quantifiers, etc.)
DANGEROUS_REGEX_PATTERNS = [
    r'\(\?[^)]*\+[^)]*\)\+',  # Nested + quantifiers
    r'\(\?[^)]*\*[^)]*\)\*',  # Nested * quantifiers
    r'\(\?[^)]*\+[^)]*\)\*',  # Mixed nested quantifiers
    r'\(\?[^)]*\*[^)]*\)\+',  # Mixed nested quantifiers
    r'\([^)]+\)\{[0-9]+,\}\{[0-9]+,\}',  # Nested repetitions
    r'(\.\*){3,}',  # Multiple .* in sequence
    r'(\.\+){3,}',  # Multiple .+ in sequence
]


class RegexTimeoutError(Exception):
    """Raised when regex execution times out."""
    pass


@contextmanager
def regex_timeout(seconds: float = 0.1):
    """
    Context manager to timeout regex operations.
    
    Note: This only works on Unix systems. On Windows, it will not timeout.
    """
    def timeout_handler(signum, frame):
        raise RegexTimeoutError("Regex execution timed out")
    
    # Only set alarm on Unix systems
    if hasattr(signal, 'SIGALRM'):
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # On Windows, just yield without timeout protection
        yield


def validate_regex_pattern(pattern: str) -> tuple[bool, str]:
    """
    Validate a regex pattern for safety.
    
    Returns:
        (is_valid, error_message)
    """
    if not pattern:
        return False, "Pattern is empty"
    
    if len(pattern) > MAX_REGEX_LENGTH:
        return False, f"Pattern too long (max {MAX_REGEX_LENGTH} chars)"
    
    # Check for dangerous patterns
    for dangerous in DANGEROUS_REGEX_PATTERNS:
        try:
            if re.search(dangerous, pattern):
                return False, "Pattern contains potentially dangerous constructs (nested quantifiers)"
        except re.error:
            pass
    
    # Try to compile the pattern
    try:
        re.compile(pattern)
    except re.error as e:
        return False, f"Invalid regex: {e}"
    
    return True, ""


def safe_regex_search(pattern: str, text: str, flags: int = 0, timeout_seconds: float = 0.1) -> bool:
    """
    Safely execute a regex search with timeout protection.
    
    Returns True if pattern matches, False otherwise (including on timeout/error).
    """
    try:
        with regex_timeout(timeout_seconds):
            return re.search(pattern, text, flags=flags) is not None
    except RegexTimeoutError:
        logger.warning(f"Regex timed out: pattern length={len(pattern)}, text length={len(text)}")
        return False
    except re.error:
        return False
    except Exception as e:
        logger.warning(f"Regex error: {e}")
        return False


@dataclass(frozen=True)
class RuleMatch:
    rule_id: int
    stop_processing: bool


class RulesService:
    """
    v1 rules:
    - trigger: message_group
    - match: contains / regex over message text
    - actions: reply / delete / warn / mute / log / start_sequence / create_ticket (ordered)
    """

    async def list_rules(self, group_id: int) -> list[dict[str, Any]]:
        async with db.session() as session:
            result = await session.execute(
                select(Rule).where(Rule.group_id == int(group_id)).order_by(Rule.priority.asc(), Rule.id.asc())
            )
            rules = list(result.scalars().all())
            out: list[dict[str, Any]] = []
            for rule in rules:
                actions_result = await session.execute(
                    select(RuleAction)
                    .where(RuleAction.rule_id == int(rule.id))
                    .order_by(RuleAction.action_order.asc(), RuleAction.id.asc())
                )
                actions = []
                for act in actions_result.scalars().all():
                    actions.append(
                        {
                            "id": int(act.id),
                            "order": int(act.action_order),
                            "type": str(act.action_type),
                            "params": str(act.params or "{}"),
                        }
                    )
                out.append(
                    {
                        "id": int(rule.id),
                        "name": str(rule.name),
                        "enabled": bool(rule.enabled),
                        "priority": int(rule.priority),
                        "trigger": str(rule.trigger),
                        "stop_processing": bool(rule.stop_processing),
                        "match_type": str(rule.match_type),
                        "pattern": str(rule.pattern),
                        "case_sensitive": bool(rule.case_sensitive),
                        "warn_threshold": int(getattr(rule, 'warn_threshold', 3) or 3),
                        "warn_escalation_action": str(getattr(rule, 'warn_escalation_action', 'kick') or 'kick'),
                        "actions": actions,
                    }
                )
            return out

    async def create_simple_rule(
        self,
        *,
        group_id: int,
        created_by: int,
        name: str,
        match_type: str,
        pattern: str,
        action_type: str,
        action_params: dict[str, Any] | None = None,
        priority: int = 100,
        stop_processing: bool = True,
        enabled: bool = True,
        trigger: str = "message_group",
        case_sensitive: bool = False,
        warn_threshold: int = 3,
        warn_escalation_action: str = "kick",
    ) -> int:
        name = (name or "").strip() or "Rule"
        pattern = (pattern or "").strip()
        if not pattern:
            raise ValueError("pattern is empty")
        if match_type not in ("contains", "regex"):
            raise ValueError("match_type must be contains|regex")
        if action_type not in ("reply", "delete", "warn", "mute", "log", "start_sequence", "create_ticket"):
            raise ValueError("action_type must be reply|delete|warn|mute|log|start_sequence|create_ticket")
        if trigger != "message_group":
            raise ValueError("only trigger=message_group is supported right now")

        if match_type == "regex":
            # Validate regex for safety (ReDoS protection)
            is_valid, error_msg = validate_regex_pattern(pattern)
            if not is_valid:
                raise ValueError(f"invalid regex: {error_msg}")
            # Also verify it compiles with the flags
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                re.compile(pattern, flags=flags)
            except re.error as e:
                raise ValueError(f"invalid regex: {e}") from e

        params = action_params or {}
        if action_type == "start_sequence":
            key = str(params.get("sequence_key") or "").strip()
            if not key:
                raise ValueError("sequence_key is required for start_sequence")
        params_json = json.dumps(params, separators=(",", ":"), ensure_ascii=False)

        # Validate warn escalation settings
        warn_threshold = max(0, min(int(warn_threshold or 3), 100))
        if warn_escalation_action not in ("kick", "ban"):
            warn_escalation_action = "kick"
        
        now = datetime.utcnow()
        rule = Rule(
            group_id=int(group_id),
            name=name,
            enabled=bool(enabled),
            priority=int(priority),
            trigger=str(trigger),
            stop_processing=bool(stop_processing),
            match_type=str(match_type),
            pattern=pattern,
            case_sensitive=bool(case_sensitive),
            warn_threshold=warn_threshold,
            warn_escalation_action=str(warn_escalation_action),
            created_by=int(created_by),
            created_at=now,
            updated_at=now,
        )
        async with db.session() as session:
            session.add(rule)
            await session.flush()
            session.add(
                RuleAction(
                    rule_id=int(rule.id),
                    action_order=1,
                    action_type=str(action_type),
                    params=params_json,
                    created_at=now,
                )
            )
            return int(rule.id)

    async def add_rule(
        self,
        *,
        group_id: int,
        created_by: int,
        name: str,
        match_type: str,
        pattern: str,
        action_type: str,
        action_params: dict[str, Any] | None = None,
        priority: int = 100,
        stop_processing: bool = True,
        enabled: bool = True,
        trigger: str = "message_group",
        case_sensitive: bool = False,
        warn_threshold: int = 3,
        warn_escalation_action: str = "kick",
    ) -> int:
        """
        Alias for create_simple_rule for API consistency.
        
        This method provides a simpler name for creating rules.
        All parameters are passed through to create_simple_rule.
        """
        return await self.create_simple_rule(
            group_id=group_id,
            created_by=created_by,
            name=name,
            match_type=match_type,
            pattern=pattern,
            action_type=action_type,
            action_params=action_params,
            priority=priority,
            stop_processing=stop_processing,
            enabled=enabled,
            trigger=trigger,
            case_sensitive=case_sensitive,
            warn_threshold=warn_threshold,
            warn_escalation_action=warn_escalation_action,
        )

    async def delete_rule(self, *, group_id: int, rule_id: int) -> bool:
        async with db.session() as session:
            rule = await session.get(Rule, int(rule_id))
            if not rule or int(rule.group_id) != int(group_id):
                return False
            # Explicitly delete actions first.
            actions_result = await session.execute(select(RuleAction).where(RuleAction.rule_id == int(rule.id)))
            for act in actions_result.scalars().all():
                await session.delete(act)
            await session.delete(rule)
            return True

    async def toggle_rule(self, *, group_id: int, rule_id: int, enabled: bool) -> bool:
        """Toggle a rule's enabled status."""
        async with db.session() as session:
            rule = await session.get(Rule, int(rule_id))
            if not rule or int(rule.group_id) != int(group_id):
                return False
            rule.enabled = enabled
            await session.commit()
            return True

    async def update_rule(
        self,
        *,
        group_id: int,
        rule_id: int,
        name: str | None = None,
        match_type: str | None = None,
        pattern: str | None = None,
        action_type: str | None = None,
        enabled: bool | None = None,
        warn_threshold: int | None = None,
        warn_escalation_action: str | None = None,
    ) -> bool:
        """Update an existing rule."""
        async with db.session() as session:
            rule = await session.get(Rule, int(rule_id))
            if not rule or int(rule.group_id) != int(group_id):
                return False
            
            # Update fields if provided
            if name is not None:
                rule.name = str(name).strip()[:100]
            if match_type is not None:
                if match_type not in ("contains", "exact", "regex", "starts_with", "ends_with"):
                    raise ValueError(f"Invalid match_type: {match_type}")
                rule.match_type = match_type
            if pattern is not None:
                pattern = str(pattern).strip()
                if not pattern:
                    raise ValueError("Pattern cannot be empty")
                # Validate regex if match_type is regex
                if (match_type or rule.match_type) == "regex":
                    is_valid, error = validate_regex_pattern(pattern)
                    if not is_valid:
                        raise ValueError(error)
                rule.pattern = pattern
            if enabled is not None:
                rule.enabled = bool(enabled)
            if warn_threshold is not None:
                rule.warn_threshold = max(0, min(int(warn_threshold), 100))
            if warn_escalation_action is not None:
                if warn_escalation_action not in ("kick", "ban"):
                    warn_escalation_action = "kick"
                rule.warn_escalation_action = warn_escalation_action
            
            # Update action if action_type changed
            if action_type is not None:
                # Get existing actions
                actions_result = await session.execute(
                    select(RuleAction).where(RuleAction.rule_id == int(rule.id))
                )
                existing_actions = list(actions_result.scalars().all())
                
                # If there's exactly one action and it's different, update it
                if len(existing_actions) == 1:
                    existing_actions[0].action_type = action_type
                elif len(existing_actions) == 0:
                    # Create new action
                    new_action = RuleAction(
                        rule_id=int(rule.id),
                        action_order=0,
                        action_type=action_type,
                        params="{}",
                    )
                    session.add(new_action)
            
            await session.commit()
            return True

    def _matches(self, rule: Rule, text: str) -> bool:
        """
        Check if a rule's pattern matches the given text.
        
        Uses safe_regex_search for regex patterns to prevent ReDoS attacks.
        """
        pattern = str(getattr(rule, "pattern", "") or "")
        if not pattern:
            return False
        match_type = str(getattr(rule, "match_type", "contains") or "contains")
        case_sensitive = bool(getattr(rule, "case_sensitive", False))
        if match_type == "contains":
            if case_sensitive:
                return pattern in text
            return pattern.lower() in text.lower()
        if match_type == "regex":
            flags = 0 if case_sensitive else re.IGNORECASE
            # Use safe regex search with timeout protection
            return safe_regex_search(pattern, text, flags=flags, timeout_seconds=0.1)
        return False

    async def _load_enabled_group_rules_with_actions(self, group_id: int) -> list[tuple[Rule, list[RuleAction]]]:
        async with db.session() as session:
            result = await session.execute(
                select(Rule)
                .where(
                    Rule.group_id == int(group_id),
                    Rule.trigger == "message_group",
                    Rule.enabled.is_(True),
                )
                .order_by(Rule.priority.asc(), Rule.id.asc())
            )
            rules = list(result.scalars().all())
            if not rules:
                return []

            rule_ids = [int(r.id) for r in rules]
            actions_result = await session.execute(
                select(RuleAction)
                .where(RuleAction.rule_id.in_(rule_ids))
                .order_by(RuleAction.rule_id.asc(), RuleAction.action_order.asc(), RuleAction.id.asc())
            )
            actions = list(actions_result.scalars().all())

        by_rule: dict[int, list[RuleAction]] = {rid: [] for rid in rule_ids}
        for act in actions:
            rid = int(getattr(act, "rule_id", 0) or 0)
            if rid in by_rule:
                by_rule[rid].append(act)

        return [(rule, by_rule.get(int(rule.id), [])) for rule in rules]

    async def test_group_text_rules(self, *, group_id: int, text: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Dry-run evaluation for the Mini App "test console".

        Returns a list of matched rules in evaluation order, including parsed actions.
        """
        limit = max(1, min(int(limit or 10), 50))
        text = str(text or "").strip()
        if not text:
            return []

        matched: list[dict[str, Any]] = []
        rules_with_actions = await self._load_enabled_group_rules_with_actions(int(group_id))
        for rule, actions in rules_with_actions:
            if not self._matches(rule, text):
                continue

            out_actions: list[dict[str, Any]] = []
            for action in actions:
                a_type = str(getattr(action, "action_type", "") or "")
                try:
                    params = json.loads(str(getattr(action, "params", "") or "{}"))
                except Exception:
                    params = {}
                out_actions.append(
                    {
                        "type": a_type,
                        "order": int(getattr(action, "action_order", 0) or 0),
                        "params": params if isinstance(params, dict) else {},
                    }
                )

            matched.append(
                {
                    "id": int(rule.id),
                    "name": str(getattr(rule, "name", "") or ""),
                    "priority": int(getattr(rule, "priority", 0) or 0),
                    "match_type": str(getattr(rule, "match_type", "") or ""),
                    "pattern": str(getattr(rule, "pattern", "") or ""),
                    "stop_processing": bool(getattr(rule, "stop_processing", False)),
                    "actions": out_actions,
                }
            )
            if bool(getattr(rule, "stop_processing", False)):
                break
            if len(matched) >= limit:
                break

        return matched

    async def _get_rule_warning_count(self, rule_id: int, telegram_id: int) -> int:
        """Get the number of warnings a user has received for a specific rule."""
        async with db.session() as session:
            result = await session.execute(
                select(RuleWarning)
                .where(
                    RuleWarning.rule_id == int(rule_id),
                    RuleWarning.telegram_id == int(telegram_id),
                )
            )
            warnings = list(result.scalars().all())
            return len(warnings)

    async def _add_rule_warning(
        self,
        *,
        rule_id: int,
        group_id: int,
        telegram_id: int,
        message_text: str | None = None,
    ) -> None:
        """Record a warning for a specific rule."""
        async with db.session() as session:
            warning = RuleWarning(
                rule_id=int(rule_id),
                group_id=int(group_id),
                telegram_id=int(telegram_id),
                warned_at=datetime.utcnow(),
                message_text=message_text[:500] if message_text else None,
            )
            session.add(warning)
            await session.commit()

    async def _clear_rule_warnings(self, rule_id: int, telegram_id: int) -> None:
        """Clear all warnings for a user on a specific rule (e.g., after escalation)."""
        async with db.session() as session:
            result = await session.execute(
                select(RuleWarning)
                .where(
                    RuleWarning.rule_id == int(rule_id),
                    RuleWarning.telegram_id == int(telegram_id),
                )
            )
            warnings = list(result.scalars().all())
            for warning in warnings:
                await session.delete(warning)
            await session.commit()

    async def apply_group_text_rules(
        self,
        *,
        message: Message,
        admin_service,
        sequence_service=None,
        ticket_service=None,
    ) -> RuleMatch | None:
        """
        Apply rules to a group text message.

        Returns:
            RuleMatch if a rule matched, else None.
        """
        if not message.text:
            return None
        group_id = int(message.chat.id)
        text = str(message.text)

        rules_with_actions = await self._load_enabled_group_rules_with_actions(group_id)
        last_match: RuleMatch | None = None

        for rule, actions in rules_with_actions:
            if not self._matches(rule, text):
                continue

            for action in actions:
                a_type = str(action.action_type)
                try:
                    params = json.loads(str(action.params or "{}"))
                except Exception:
                    params = {}

                if a_type == "delete":
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    continue

                if a_type == "reply":
                    resp = str(params.get("text") or "").strip()
                    if resp:
                        parse_mode = params.get("parse_mode")
                        try:
                            await message.reply(resp, parse_mode=parse_mode)
                        except Exception:
                            pass
                    continue

                if a_type == "warn":
                    user_id = int(message.from_user.id)
                    rule_id = int(rule.id)
                    
                    # Get warning threshold and escalation action from rule
                    warn_threshold = int(getattr(rule, 'warn_threshold', 3) or 3)
                    escalation_action = str(getattr(rule, 'warn_escalation_action', 'kick') or 'kick')
                    
                    # Get current warning count for this rule
                    current_warnings = await self._get_rule_warning_count(rule_id, user_id)
                    
                    # Check if we should escalate (threshold > 0 means escalation is enabled)
                    if warn_threshold > 0 and current_warnings >= warn_threshold:
                        # Escalate: kick or ban the user
                        try:
                            if escalation_action == "ban":
                                await admin_service.ban_user(
                                    bot=message.bot,
                                    group_id=group_id,
                                    user_id=user_id,
                                    admin_id=int(message.bot.id),
                                    reason=f"Rule: {rule.name} (exceeded {warn_threshold} warnings)",
                                )
                            else:  # kick
                                await admin_service.kick_user(
                                    bot=message.bot,
                                    group_id=group_id,
                                    user_id=user_id,
                                    admin_id=int(message.bot.id),
                                    reason=f"Rule: {rule.name} (exceeded {warn_threshold} warnings)",
                                )
                            # Clear warnings after escalation
                            await self._clear_rule_warnings(rule_id, user_id)
                        except Exception as e:
                            logger.error(f"Failed to escalate rule warning: {e}")
                    else:
                        # Issue warning and track it
                        try:
                            await admin_service.warn_user(
                                bot=message.bot,
                                group_id=group_id,
                                user_id=user_id,
                                admin_id=int(message.bot.id),
                                reason=f"Rule: {rule.name} ({current_warnings + 1}/{warn_threshold})",
                            )
                            # Record the warning
                            await self._add_rule_warning(
                                rule_id=rule_id,
                                group_id=group_id,
                                telegram_id=user_id,
                                message_text=str(message.text or ""),
                            )
                        except Exception as e:
                            logger.error(f"Failed to warn user for rule: {e}")
                    continue

                if a_type == "mute":
                    duration = int(params.get("duration_seconds") or 300)
                    duration = max(30, min(duration, 7 * 24 * 3600))
                    try:
                        await admin_service.mute_user(
                            bot=message.bot,
                            group_id=group_id,
                            user_id=int(message.from_user.id),
                            admin_id=int(message.bot.id),
                            duration=duration,
                            reason=f"Rule: {rule.name}",
                        )
                    except Exception:
                        pass
                    continue

                if a_type == "log":
                    custom = str(params.get("text") or "").strip()
                    msg_text = str(message.text or "")
                    msg_text = msg_text.replace("\x00", "")
                    snippet = msg_text if len(msg_text) <= 800 else (msg_text[:797] + "...")
                    reason = custom or f"Rule matched: {rule.name}"
                    if snippet:
                        reason = f"{reason}\n\nMessage:\n{snippet}"
                    if len(reason) > 1500:
                        reason = reason[:1497] + "..."
                    try:
                        await admin_service.log_custom_action(
                            message.bot,
                            group_id,
                            actor_id=int(message.bot.id),
                            target_id=int(message.from_user.id),
                            action="rule_log",
                            reason=reason,
                        )
                    except Exception:
                        pass
                    continue

                if a_type == "start_sequence":
                    if not sequence_service:
                        continue
                    seq_key = str(params.get("sequence_key") or "").strip()
                    if not seq_key:
                        continue
                    trigger_key = str(params.get("trigger_key") or "").strip() or f"rule:{int(rule.id)}"
                    try:
                        await sequence_service.start_sequence_by_key(
                            group_id=group_id,
                            telegram_id=int(message.from_user.id),
                            sequence_key=seq_key,
                            trigger_key=trigger_key,
                        )
                    except Exception:
                        pass
                    continue

                if a_type == "create_ticket":
                    if not ticket_service:
                        continue
                    subject = str(params.get("subject") or "").strip() or f"Rule: {rule.name}"
                    body = str(message.text or "").strip()
                    if not body:
                        continue
                    ticket_msg = f"Rule matched: {rule.name}\n\n{body}"
                    if len(ticket_msg) > 2000:
                        ticket_msg = ticket_msg[:1997] + "..."
                    try:
                        await ticket_service.create_ticket(
                            bot=message.bot,
                            group_id=group_id,
                            user_id=int(message.from_user.id),
                            subject=subject,
                            message=ticket_msg,
                        )
                    except Exception:
                        pass
                    continue

            last_match = RuleMatch(rule_id=int(rule.id), stop_processing=bool(rule.stop_processing))
            if bool(rule.stop_processing):
                return last_match

        return last_match
