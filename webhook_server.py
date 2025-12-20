"""Webhook server for production deployment - clean architecture."""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from aiogram.types import Update
from aiogram.exceptions import TelegramAPIError
from pydantic import BaseModel

from bot.main import TelegramBot
from bot.config import Config
from bot.utils.permissions import can_delete_messages, can_pin_messages, can_restrict_members, can_user, is_bot_admin
from bot.utils.webapp_auth import WebAppAuthError, validate_webapp_init_data

# Don't configure logging here - it's configured in bot/main.py
logger = logging.getLogger(__name__)

# Global bot instance
telegram_bot: TelegramBot = None
config = Config.from_env()

def _update_kind(update: Update) -> str:
    if getattr(update, "message", None) is not None:
        return "message"
    if getattr(update, "edited_message", None) is not None:
        return "edited_message"
    if getattr(update, "callback_query", None) is not None:
        return "callback_query"
    if getattr(update, "chat_join_request", None) is not None:
        return "chat_join_request"
    if getattr(update, "my_chat_member", None) is not None:
        return "my_chat_member"
    if getattr(update, "chat_member", None) is not None:
        return "chat_member"
    return "other"


def _safe_command_summary(text: str) -> str | None:
    if not text or not text.startswith("/"):
        return None
    head, *rest = text.split(maxsplit=1)
    cmd = head.split("@", 1)[0]
    if cmd == "/start" and rest:
        payload = rest[0].strip()
        if payload.startswith("cfg_"):
            return "cmd=/start payload=cfg"
        if payload.startswith("ver_"):
            return "cmd=/start payload=ver"
        return "cmd=/start payload=other"
    return f"cmd={cmd}"

def _truncate(s: str, *, max_len: int = 140) -> str:
    s = (s or "").replace("\n", " ").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _log_update_summary(update: Update) -> None:
    try:
        kind = _update_kind(update)
        if kind in ("message", "edited_message"):
            msg = update.message or update.edited_message
            chat = getattr(msg, "chat", None)
            chat_id = getattr(chat, "id", None)
            chat_type = getattr(chat, "type", None)
            from_user = getattr(msg, "from_user", None)
            from_id = getattr(from_user, "id", None)

            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            cmd_summary = _safe_command_summary(text)

            # Avoid logging raw user text; log commands everywhere. For non-command messages, log only metadata.
            if cmd_summary:
                logger.info(
                    "tg_update=%s kind=%s chat=%s(%s) from=%s %s",
                    update.update_id,
                    kind,
                    chat_id,
                    chat_type,
                    from_id,
                    cmd_summary,
                )
                return

            try:
                content_type = str(getattr(msg, "content_type", None) or "")
            except Exception:
                content_type = ""

            logger.info(
                "tg_update=%s kind=%s chat=%s(%s) from=%s ct=%s text_len=%s text=\"%s\"",
                update.update_id,
                kind,
                chat_id,
                chat_type,
                from_id,
                content_type or "unknown",
                len(text),
                _truncate(text),
            )
            return

        if kind == "callback_query":
            cb = update.callback_query
            from_id = getattr(getattr(cb, "from_user", None), "id", None)
            data = getattr(cb, "data", None) or ""
            msg = getattr(cb, "message", None)
            chat = getattr(msg, "chat", None)
            chat_id = getattr(chat, "id", None)
            chat_type = getattr(chat, "type", None)
            logger.info(
                "tg_update=%s kind=callback_query chat=%s(%s) from=%s data=%s",
                update.update_id,
                chat_id,
                chat_type,
                from_id,
                _truncate(data),
            )
            return

        if kind == "chat_join_request":
            req = update.chat_join_request
            chat = getattr(req, "chat", None)
            chat_id = getattr(chat, "id", None)
            chat_type = getattr(chat, "type", None)
            from_user = getattr(req, "from_user", None)
            from_id = getattr(from_user, "id", None)
            user_chat_id = getattr(req, "user_chat_id", None)
            logger.info(
                "tg_update=%s kind=chat_join_request chat=%s(%s) from=%s user_chat_id=%s",
                update.update_id,
                chat_id,
                chat_type,
                from_id,
                user_chat_id,
            )
            return

        if kind in ("chat_member", "my_chat_member"):
            ev = update.chat_member if kind == "chat_member" else update.my_chat_member
            chat = getattr(ev, "chat", None)
            chat_id = getattr(chat, "id", None)
            chat_type = getattr(chat, "type", None)
            user = getattr(getattr(ev, "from_user", None), "id", None)
            old = getattr(getattr(ev, "old_chat_member", None), "status", None)
            new = getattr(getattr(ev, "new_chat_member", None), "status", None)
            target = getattr(getattr(getattr(ev, "new_chat_member", None), "user", None), "id", None)
            logger.info(
                "tg_update=%s kind=%s chat=%s(%s) actor=%s target=%s %s->%s",
                update.update_id,
                kind,
                chat_id,
                chat_type,
                user,
                target,
                old,
                new,
            )
            return

        logger.info("tg_update=%s kind=%s", update.update_id, kind)
    except Exception:
        return


def _get_admin_token_from_request(request: Request) -> str | None:
    # Prefer Authorization: Bearer <token>, fallback to X-Admin-Token header
    # NOTE: Query params (?token=) removed for security - they leak to logs/proxies
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        parts = auth.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    token = request.headers.get("x-admin-token") or request.headers.get("X-Admin-Token")
    return token.strip() if token else None


def _is_admin_request(request: Request) -> bool:
    expected = (getattr(config, "admin_api_token", "") or os.getenv("ADMIN_API_TOKEN", "")).strip()
    if not expected:
        return False
    provided = _get_admin_token_from_request(request)
    return bool(provided) and provided == expected


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global telegram_bot
    
    logger.info("🚀 Starting Webhook Server...")
    
    try:
        # Initialize bot
        telegram_bot = TelegramBot(config)
        await telegram_bot.initialize()
        await telegram_bot.start()
        
        # Set webhook with secret token for validation
        webhook_url = f"{config.webhook_url}{config.webhook_path}"
        webhook_kwargs = {
            "url": webhook_url,
            "allowed_updates": telegram_bot.get_dispatcher().resolve_used_update_types()
        }
        # Add secret token if configured (highly recommended for security)
        if config.webhook_secret:
            webhook_kwargs["secret_token"] = config.webhook_secret
            logger.info("🔒 Webhook secret token configured")
        else:
            logger.warning("⚠️ WEBHOOK_SECRET not set - webhook requests are NOT validated!")
        
        await telegram_bot.get_bot().set_webhook(**webhook_kwargs)
        logger.info(f"✅ Webhook set to: {webhook_url}")

        yield
        
        # Shutdown
        logger.info("🛑 Shutting down Webhook Server...")
        await telegram_bot.get_bot().delete_webhook()
        await telegram_bot.stop()
        
    except Exception as e:
        logger.error(f"❌ Failed to start webhook server: {e}", exc_info=True)
        raise


# Create FastAPI app
app = FastAPI(
    lifespan=lifespan,
    title="Telegram Verification Bot",
    description="Biometric verification bot powered by Mercle SDK",
    version="2.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


class _InitDataPayload(BaseModel):
    initData: str


class _GroupSettingsUpdate(BaseModel):
    initData: str
    verification_enabled: bool | None = None
    verification_timeout: int | None = None
    action_on_timeout: str | None = None  # kick|mute
    join_gate_enabled: bool | None = None
    require_rules_acceptance: bool | None = None
    captcha_enabled: bool | None = None
    captcha_style: str | None = None  # button|math
    captcha_max_attempts: int | None = None
    block_no_username: bool | None = None
    antiflood_enabled: bool | None = None
    antiflood_limit: int | None = None
    antiflood_mute_seconds: int | None = None
    antiflood_action: str | None = None  # mute|warn|kick|ban
    antiflood_delete_messages: bool | None = None
    antiflood_warn_threshold: int | None = None
    silent_automations: bool | None = None
    raid_mode_enabled: bool | None = None
    raid_mode_minutes: int | None = None
    raid_mode_duration_minutes: int | None = None  # Alias for raid_mode_minutes
    lock_links: bool | None = None
    lock_media: bool | None = None
    logs_mode: str | None = None  # off|group


class _LogsTestPayload(BaseModel):
    initData: str


class _BroadcastPayload(BaseModel):
    initData: str
    text: str
    delay_seconds: int | None = 0
    parse_mode: str | None = "Markdown"  # Markdown|HTML|None
    disable_web_page_preview: bool | None = True


class _BroadcastMultiPayload(BaseModel):
    initData: str
    group_ids: list[int]
    text: str
    delay_seconds: int | None = 0
    parse_mode: str | None = "Markdown"  # Markdown|HTML|None
    disable_web_page_preview: bool | None = True


class _BroadcastDmPayload(BaseModel):
    initData: str
    text: str
    delay_seconds: int | None = 0
    parse_mode: str | None = "Markdown"  # Markdown|HTML|None
    disable_web_page_preview: bool | None = True
    max_targets: int | None = 5000


class _DmSubscribersPayload(BaseModel):
    initData: str


class _BroadcastHistoryPayload(BaseModel):
    initData: str
    limit: int | None = 20


class _OnboardingUpdatePayload(BaseModel):
    initData: str
    enabled: bool
    delay_seconds: int = 0
    text: str = ""
    parse_mode: str | None = "Markdown"  # Markdown|HTML|None


class _OnboardingGetPayload(BaseModel):
    initData: str


class _OnboardingStepPayload(BaseModel):
    delay_seconds: int = 0
    text: str = ""
    parse_mode: str | None = "Markdown"  # Markdown|HTML|None


class _OnboardingStepsUpdatePayload(BaseModel):
    initData: str
    enabled: bool
    steps: list[_OnboardingStepPayload] = []


class _RulesListPayload(BaseModel):
    initData: str


class _RuleCreatePayload(BaseModel):
    initData: str
    name: str = "Rule"
    match_type: str = "contains"  # contains|regex
    pattern: str
    case_sensitive: bool = False
    action_type: str  # reply|delete|warn|mute|log|start_sequence|create_ticket
    reply_text: str | None = None
    mute_duration_seconds: int | None = None
    log_text: str | None = None
    sequence_key: str | None = None
    sequence_trigger_key: str | None = None
    ticket_subject: str | None = None
    priority: int = 100
    stop_processing: bool = True


class _RuleTestPayload(BaseModel):
    initData: str
    text: str
    limit: int | None = 10


class _RuleDeletePayload(BaseModel):
    initData: str
    rule_id: int


class _TicketsListPayload(BaseModel):
    initData: str
    status: str | None = "open"  # open|closed


def _require_container() -> tuple[TelegramBot, object]:
    if not telegram_bot or not telegram_bot.is_running() or not telegram_bot.get_container():
        raise HTTPException(status_code=503, detail="bot not ready")
    return telegram_bot, telegram_bot.get_container()


async def _bot_preflight(bot, group_id: int) -> dict:
    try:
        bot_info = await bot.get_me()
        bot_id = int(bot_info.id)
    except Exception:
        bot_id = 0

    bot_admin = False
    restrict_ok = False
    delete_ok = False
    pin_ok = False
    join_by_request = False
    invite_ok = False

    try:
        bot_admin = await is_bot_admin(bot, group_id)
    except Exception:
        bot_admin = False

    if bot_id:
        try:
            restrict_ok = await can_restrict_members(bot, group_id, bot_id)
        except Exception:
            restrict_ok = False
        try:
            delete_ok = await can_delete_messages(bot, group_id, bot_id)
        except Exception:
            delete_ok = False
        try:
            pin_ok = await can_pin_messages(bot, group_id, bot_id)
        except Exception:
            pin_ok = False
        try:
            member = await bot.get_chat_member(group_id, bot_id)
            if member.status == "creator":
                invite_ok = True
            else:
                invite_ok = member.status == "administrator" and bool(getattr(member, "can_invite_users", False))
        except Exception:
            invite_ok = False

    try:
        chat = await bot.get_chat(group_id)
        join_by_request = bool(getattr(chat, "join_by_request", False))
    except Exception:
        join_by_request = False

    return {
        "bot_admin": bot_admin,
        "restrict_ok": restrict_ok,
        "delete_ok": delete_ok,
        "pin_ok": pin_ok,
        "join_by_request": join_by_request,
        "invite_ok": invite_ok,
    }


@app.get("/app")
async def mini_app():
    """Telegram Mini App (settings UI)."""
    try:
        with open("static/app.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Mini App not deployed</h1>", status_code=404)


@app.post("/api/app/bootstrap")
async def app_bootstrap(payload: _InitDataPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user = auth.user
    user_id = int(user["id"])

    groups = await container.group_service.list_groups()
    allowed = []
    now = datetime.utcnow()
    for group in groups[:200]:
        gid = int(group.group_id)
        try:
            if await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
                preflight = await _bot_preflight(bot_obj.get_bot(), gid)
                onboarding = {}
                try:
                    onboarding = await container.sequence_service.get_onboarding_sequence(gid)
                except Exception:
                    onboarding = {"enabled": False, "delay_seconds": 0, "text": "", "parse_mode": "Markdown"}
                
                # Get member count from Telegram
                member_count = 0
                try:
                    member_count = await bot_obj.get_bot().get_chat_member_count(gid)
                except Exception:
                    pass
                
                allowed.append(
                    {
                        "group_id": gid,
                        "group_name": group.group_name,
                        "member_count": member_count,
                        "settings": {
                            "verification_enabled": bool(getattr(group, "verification_enabled", True)),
                            "verification_timeout": int(getattr(group, "verification_timeout", 300) or 300),
                            "action_on_timeout": "kick" if bool(getattr(group, "kick_unverified", False)) else "mute",
                            "join_gate_enabled": bool(getattr(group, "join_gate_enabled", False)),
                            "require_rules_acceptance": bool(getattr(group, "require_rules_acceptance", False)),
                            "captcha_enabled": bool(getattr(group, "captcha_enabled", False)),
                            "captcha_style": str(getattr(group, "captcha_style", "button") or "button"),
                            "captcha_max_attempts": int(getattr(group, "captcha_max_attempts", 3) or 3),
                            "block_no_username": bool(getattr(group, "block_no_username", False)),
                            "antiflood_enabled": bool(getattr(group, "antiflood_enabled", False)),
                            "antiflood_limit": int(getattr(group, "antiflood_limit", 10) or 10),
                            "antiflood_mute_seconds": int(getattr(group, "antiflood_mute_seconds", 300) or 300),
                            "antiflood_action": str(getattr(group, "antiflood_action", "mute") or "mute"),
                            "antiflood_delete_messages": bool(getattr(group, "antiflood_delete_messages", True)),
                            "antiflood_warn_threshold": int(getattr(group, "antiflood_warn_threshold", 0) or 0),
                            "silent_automations": bool(getattr(group, "silent_automations", False)),
                            "raid_mode_enabled": bool(getattr(group, "raid_mode_until", None) and getattr(group, "raid_mode_until") > now),
                            "raid_mode_remaining_seconds": max(
                                0,
                                int((getattr(group, "raid_mode_until") - now).total_seconds()),
                            )
                            if getattr(group, "raid_mode_until", None) and getattr(group, "raid_mode_until") > now
                            else 0,
                            "lock_links": bool(getattr(group, "lock_links", False)),
                            "lock_media": bool(getattr(group, "lock_media", False)),
                            "logs_enabled": bool(getattr(group, "logs_enabled", False)),
                            "logs_chat_id": int(group.logs_chat_id) if getattr(group, "logs_chat_id", None) else None,
                            "logs_thread_id": int(group.logs_thread_id) if getattr(group, "logs_thread_id", None) else None,
                        },
                        "onboarding": onboarding,
                        "preflight": preflight,
                    }
                )
        except Exception:
            continue

    # Check user verification status
    is_verified = await container.user_manager.is_verified(user_id)
    user_data = None
    verified_until = None
    mercle_user_id = None
    
    try:
        from database.db import db
        async with db.session() as session:
            from sqlalchemy import select
            from database.models import User
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            db_user = result.scalar_one_or_none()
            if db_user:
                verified_until = db_user.verified_until.isoformat() if db_user.verified_until else None
                mercle_user_id = db_user.mercle_user_id
    except Exception as e:
        logger.warning(f"Failed to fetch user verification details: {e}")

    return {
        "user": user,
        "groups": allowed,
        "verification": {
            "is_verified": is_verified,
            "verified_until": verified_until,
            "mercle_user_id": mercle_user_id
        }
    }


@app.post("/api/app/group/{group_id}/settings")
async def app_update_group_settings(group_id: int, payload: _GroupSettingsUpdate):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    if payload.require_rules_acceptance is True:
        group = await container.group_service.get_or_create_group(gid)
        if not (str(getattr(group, "rules_text", "") or "").strip()):
            raise HTTPException(status_code=400, detail="rules_text is not set (use /setrules first)")

    # Join gate is MANDATORY - validation removed
    # The join_by_request check was blocking settings saves
    # Runtime validation happens in join_requests.py handler instead
    # if payload.join_gate_enabled is True:
    #     preflight = await _bot_preflight(bot_obj.get_bot(), gid)
    #     if not preflight.get("join_by_request", False):
    #         raise HTTPException(status_code=400, detail="join requests are disabled (join_by_request=false)")
    #     if not preflight.get("invite_ok", False):
    #         raise HTTPException(status_code=400, detail="bot is missing Invite Users permission")

    action_on_timeout = payload.action_on_timeout
    if action_on_timeout is not None and action_on_timeout not in ("kick", "mute"):
        raise HTTPException(status_code=400, detail="action_on_timeout must be kick|mute")

    if payload.captcha_style is not None:
        style = str(payload.captcha_style or "").strip() or "button"
        if style not in ("button", "math"):
            raise HTTPException(status_code=400, detail="captcha_style must be button|math")

    if payload.captcha_max_attempts is not None:
        mx = int(payload.captcha_max_attempts or 0)
        if mx < 1 or mx > 10:
            raise HTTPException(status_code=400, detail="captcha_max_attempts must be 1..10")

    if payload.antiflood_mute_seconds is not None:
        secs = int(payload.antiflood_mute_seconds or 0)
        if secs < 30 or secs > 24 * 60 * 60:
            raise HTTPException(status_code=400, detail="antiflood_mute_seconds must be 30..86400")

    logs_mode = payload.logs_mode
    if logs_mode is not None and logs_mode not in ("off", "group"):
        raise HTTPException(status_code=400, detail="logs_mode must be off|group")

    if logs_mode == "off":
        await container.group_service.update_setting(gid, logs_enabled=False)
    elif logs_mode == "group":
        await container.group_service.update_setting(gid, logs_enabled=True, logs_chat_id=gid, logs_thread_id=None)

    await container.group_service.update_setting(
        gid,
        verification_enabled=payload.verification_enabled,
        verification_timeout=payload.verification_timeout,
        action_on_timeout=action_on_timeout,
        join_gate_enabled=payload.join_gate_enabled,
        require_rules_acceptance=payload.require_rules_acceptance,
        captcha_enabled=payload.captcha_enabled,
        captcha_style=payload.captcha_style,
        captcha_max_attempts=payload.captcha_max_attempts,
        block_no_username=payload.block_no_username,
        antiflood_enabled=payload.antiflood_enabled,
        antiflood_limit=payload.antiflood_limit,
        antiflood_mute_seconds=payload.antiflood_mute_seconds,
        antiflood_action=payload.antiflood_action,
        antiflood_delete_messages=payload.antiflood_delete_messages,
        antiflood_warn_threshold=payload.antiflood_warn_threshold,
        silent_automations=payload.silent_automations,
        raid_mode_enabled=payload.raid_mode_enabled,
        raid_mode_minutes=payload.raid_mode_minutes or payload.raid_mode_duration_minutes,
    )

    if payload.lock_links is not None or payload.lock_media is not None:
        await container.lock_service.set_lock(gid, lock_links=payload.lock_links, lock_media=payload.lock_media)

    group = await container.group_service.get_or_create_group(gid)
    preflight = await _bot_preflight(bot_obj.get_bot(), gid)
    now = datetime.utcnow()

    return {
        "group_id": gid,
        "group_name": group.group_name,
        "settings": {
            "verification_enabled": bool(getattr(group, "verification_enabled", True)),
            "verification_timeout": int(getattr(group, "verification_timeout", 300) or 300),
            "action_on_timeout": "kick" if bool(getattr(group, "kick_unverified", False)) else "mute",
            "join_gate_enabled": bool(getattr(group, "join_gate_enabled", False)),
            "require_rules_acceptance": bool(getattr(group, "require_rules_acceptance", False)),
            "captcha_enabled": bool(getattr(group, "captcha_enabled", False)),
            "captcha_style": str(getattr(group, "captcha_style", "button") or "button"),
            "captcha_max_attempts": int(getattr(group, "captcha_max_attempts", 3) or 3),
            "block_no_username": bool(getattr(group, "block_no_username", False)),
            "antiflood_enabled": bool(getattr(group, "antiflood_enabled", False)),
            "antiflood_limit": int(getattr(group, "antiflood_limit", 10) or 10),
            "antiflood_mute_seconds": int(getattr(group, "antiflood_mute_seconds", 300) or 300),
            "antiflood_action": str(getattr(group, "antiflood_action", "mute") or "mute"),
            "antiflood_delete_messages": bool(getattr(group, "antiflood_delete_messages", True)),
            "antiflood_warn_threshold": int(getattr(group, "antiflood_warn_threshold", 0) or 0),
            "silent_automations": bool(getattr(group, "silent_automations", False)),
            "raid_mode_enabled": bool(getattr(group, "raid_mode_until", None) and getattr(group, "raid_mode_until") > now),
            "raid_mode_remaining_seconds": max(
                0,
                int((getattr(group, "raid_mode_until") - now).total_seconds()),
            )
            if getattr(group, "raid_mode_until", None) and getattr(group, "raid_mode_until") > now
            else 0,
            "lock_links": bool(getattr(group, "lock_links", False)),
            "lock_media": bool(getattr(group, "lock_media", False)),
            "logs_enabled": bool(getattr(group, "logs_enabled", False)),
            "logs_chat_id": int(group.logs_chat_id) if getattr(group, "logs_chat_id", None) else None,
            "logs_thread_id": int(group.logs_thread_id) if getattr(group, "logs_thread_id", None) else None,
        },
        "preflight": preflight,
    }


@app.post("/api/app/group/{group_id}/logs/test")
async def app_test_logs_destination(group_id: int, payload: _LogsTestPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    group = await container.group_service.get_or_create_group(gid)
    if not getattr(group, "logs_enabled", False) or not getattr(group, "logs_chat_id", None):
        raise HTTPException(status_code=400, detail="logs destination is off")

    dest_chat_id = int(group.logs_chat_id)
    thread_id = int(group.logs_thread_id) if getattr(group, "logs_thread_id", None) else None

    bot = bot_obj.get_bot()
    try:
        bot_info = await bot.get_me()
        bot_member = await bot.get_chat_member(dest_chat_id, bot_info.id)
        if getattr(bot_member, "status", None) not in ("administrator", "creator", "member"):
            raise RuntimeError(f"bot status: {getattr(bot_member, 'status', None)}")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="bot cannot access logs destination (add bot there; for channels, make it admin)",
        )

    kwargs = {"disable_web_page_preview": True}
    if thread_id:
        kwargs["message_thread_id"] = thread_id

    await bot.send_message(
        chat_id=dest_chat_id,
        text=f"<b>Log test</b>\nGroup: <code>{gid}</code>\nBy: <code>{user_id}</code>",
        parse_mode="HTML",
        **kwargs,
    )

    return {"group_id": gid, "ok": True, "logs_chat_id": dest_chat_id, "logs_thread_id": thread_id}


class _LogsChannelPayload(BaseModel):
    initData: str
    chat_id: int


@app.post("/api/app/group/{group_id}/logs/channel")
async def app_set_logs_channel(group_id: int, payload: _LogsChannelPayload):
    """Set the logs destination channel/group."""
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    logs_chat_id = int(payload.chat_id)
    
    # Verify bot can access the destination
    bot = bot_obj.get_bot()
    try:
        bot_info = await bot.get_me()
        bot_member = await bot.get_chat_member(logs_chat_id, bot_info.id)
        if getattr(bot_member, "status", None) not in ("administrator", "creator", "member"):
            raise HTTPException(status_code=400, detail="Bot is not a member of that chat")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot access chat: {e}")
    
    # Update group settings
    await container.group_service.update_setting(
        gid,
        logs_enabled=True,
        logs_chat_id=logs_chat_id
    )
    
    return {"group_id": gid, "ok": True, "logs_chat_id": logs_chat_id}


@app.post("/api/app/group/{group_id}/broadcast")
async def app_group_broadcast(group_id: int, payload: _BroadcastPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    if len(text) > 4096:
        raise HTTPException(status_code=400, detail="text is too long")

    parse_mode = payload.parse_mode
    if parse_mode is not None and parse_mode not in ("Markdown", "HTML"):
        raise HTTPException(status_code=400, detail="parse_mode must be Markdown|HTML|null")

    delay_seconds = int(payload.delay_seconds or 0)
    if delay_seconds < 0:
        raise HTTPException(status_code=400, detail="delay_seconds must be >= 0")
    if delay_seconds > 7 * 24 * 3600:
        raise HTTPException(status_code=400, detail="delay_seconds is too large (max 7 days)")

    try:
        broadcast_id = await container.broadcast_service.create_group_broadcast(
            created_by=user_id,
            chat_ids=[gid],
            text=text,
            delay_seconds=delay_seconds,
            parse_mode=parse_mode,
            disable_web_page_preview=bool(payload.disable_web_page_preview),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"broadcast_id": int(broadcast_id), "group_id": gid, "status": "queued", "delay_seconds": delay_seconds}


@app.post("/api/app/broadcast")
async def app_broadcast(payload: _BroadcastMultiPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])

    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    if len(text) > 4096:
        raise HTTPException(status_code=400, detail="text is too long")

    parse_mode = payload.parse_mode
    if parse_mode is not None and parse_mode not in ("Markdown", "HTML"):
        raise HTTPException(status_code=400, detail="parse_mode must be Markdown|HTML|null")

    delay_seconds = int(payload.delay_seconds or 0)
    if delay_seconds < 0:
        raise HTTPException(status_code=400, detail="delay_seconds must be >= 0")
    if delay_seconds > 7 * 24 * 3600:
        raise HTTPException(status_code=400, detail="delay_seconds is too large (max 7 days)")

    raw_ids = payload.group_ids or []
    if not raw_ids:
        raise HTTPException(status_code=400, detail="group_ids is empty")

    allowed: list[int] = []
    skipped: list[int] = []
    seen: set[int] = set()
    for raw in raw_ids[:100]:
        try:
            gid = int(raw)
        except Exception:
            continue
        if gid in seen:
            continue
        seen.add(gid)
        try:
            if await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
                allowed.append(gid)
            else:
                skipped.append(gid)
        except Exception:
            skipped.append(gid)

    if not allowed:
        raise HTTPException(status_code=403, detail="no allowed groups")

    try:
        broadcast_id = await container.broadcast_service.create_group_broadcast(
            created_by=user_id,
            chat_ids=allowed,
            text=text,
            delay_seconds=delay_seconds,
            parse_mode=parse_mode,
            disable_web_page_preview=bool(payload.disable_web_page_preview),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "broadcast_id": int(broadcast_id),
        "total_targets": len(allowed),
        "skipped_group_ids": skipped,
        "status": "queued",
        "delay_seconds": delay_seconds,
    }


async def _require_any_settings_access(bot_obj: TelegramBot, *, user_id: int, container) -> None:
    """Check if user has settings access in ANY group."""
    groups = await container.group_service.list_groups()
    for group in groups[:200]:
        try:
            if await can_user(bot_obj.get_bot(), int(group.group_id), int(user_id), "settings"):
                return
        except Exception:
            continue
    raise HTTPException(status_code=403, detail="not allowed")


def _require_broadcast_admin(user_id: int) -> None:
    """
    Check if user is allowed to send DM broadcasts.
    
    DM broadcasts reach ALL bot subscribers across ALL groups, so this is a 
    highly privileged operation. Only users in BROADCAST_ADMIN_IDS can do this.
    
    If BROADCAST_ADMIN_IDS is not configured, DM broadcasts are disabled entirely.
    """
    if not config.broadcast_admin_ids:
        logger.warning(f"DM broadcast attempted by {user_id} but BROADCAST_ADMIN_IDS not configured")
        raise HTTPException(
            status_code=403, 
            detail="DM broadcasts are disabled. Configure BROADCAST_ADMIN_IDS to enable."
        )
    
    if user_id not in config.broadcast_admin_ids:
        logger.warning(f"DM broadcast attempted by unauthorized user {user_id}")
        raise HTTPException(status_code=403, detail="not authorized for DM broadcasts")


@app.post("/api/app/dm/subscribers")
async def app_dm_subscribers(payload: _DmSubscribersPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    # DM subscriber count is only visible to broadcast admins
    _require_broadcast_admin(user_id)

    count = await container.dm_subscriber_service.count_deliverable()
    return {"deliverable": int(count)}


@app.post("/api/app/broadcast/dm")
async def app_broadcast_dm(payload: _BroadcastDmPayload):
    """
    Send a DM broadcast to all bot subscribers.
    
    SECURITY: This is a highly privileged operation. Only users listed in 
    BROADCAST_ADMIN_IDS environment variable can use this endpoint.
    """
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    # CRITICAL: Only broadcast admins can send DM broadcasts
    _require_broadcast_admin(user_id)
    logger.info(f"DM broadcast initiated by authorized admin {user_id}")

    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    if len(text) > 4096:
        raise HTTPException(status_code=400, detail="text is too long")

    parse_mode = payload.parse_mode
    if parse_mode is not None and parse_mode not in ("Markdown", "HTML"):
        raise HTTPException(status_code=400, detail="parse_mode must be Markdown|HTML|null")

    delay_seconds = int(payload.delay_seconds or 0)
    if delay_seconds < 0:
        raise HTTPException(status_code=400, detail="delay_seconds must be >= 0")
    if delay_seconds > 7 * 24 * 3600:
        raise HTTPException(status_code=400, detail="delay_seconds is too large (max 7 days)")

    max_targets = int(payload.max_targets or 5000)
    max_targets = max(1, min(max_targets, 20000))

    try:
        broadcast_id, total_targets = await container.broadcast_service.create_dm_broadcast(
            created_by=user_id,
            text=text,
            delay_seconds=delay_seconds,
            parse_mode=parse_mode,
            disable_web_page_preview=bool(payload.disable_web_page_preview),
            max_targets=max_targets,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "broadcast_id": int(broadcast_id),
        "total_targets": int(total_targets),
        "status": "queued",
        "delay_seconds": delay_seconds,
        "max_targets": max_targets,
    }


@app.post("/api/app/group/{group_id}/broadcasts")
async def app_group_broadcasts(group_id: int, payload: _BroadcastHistoryPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    limit = int(payload.limit or 20)
    broadcasts = await container.broadcast_service.list_recent_for_group(group_id=gid, limit=limit)
    return {"group_id": gid, "broadcasts": broadcasts}


@app.post("/api/app/group/{group_id}/onboarding")
async def app_update_onboarding(group_id: int, payload: _OnboardingUpdatePayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    parse_mode = payload.parse_mode
    if parse_mode is not None and parse_mode not in ("Markdown", "HTML"):
        raise HTTPException(status_code=400, detail="parse_mode must be Markdown|HTML|null")

    try:
        onboarding = await container.sequence_service.upsert_onboarding_sequence(
            group_id=gid,
            admin_id=user_id,
            enabled=bool(payload.enabled),
            delay_seconds=int(payload.delay_seconds or 0),
            text=str(payload.text or ""),
            parse_mode=parse_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"group_id": gid, "onboarding": onboarding}


@app.post("/api/app/group/{group_id}/onboarding/get")
async def app_get_onboarding(group_id: int, payload: _OnboardingGetPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    onboarding = await container.sequence_service.get_onboarding_sequence_steps(gid)
    return {"group_id": gid, "onboarding": onboarding}


@app.post("/api/app/group/{group_id}/onboarding/steps")
async def app_update_onboarding_steps(group_id: int, payload: _OnboardingStepsUpdatePayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    try:
        onboarding = await container.sequence_service.upsert_onboarding_sequence_steps(
            group_id=gid,
            admin_id=user_id,
            enabled=bool(payload.enabled),
            steps=[s.model_dump() for s in (payload.steps or [])],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"group_id": gid, "onboarding": onboarding}


@app.post("/api/app/group/{group_id}/rules")
async def app_list_rules(group_id: int, payload: _RulesListPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    rules = await container.rules_service.list_rules(gid)
    return {"group_id": gid, "rules": rules}


@app.post("/api/app/group/{group_id}/rules/test")
async def app_test_rules(group_id: int, payload: _RuleTestPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    text = str(payload.text or "").strip()
    if not text:
        return {"group_id": gid, "matches": []}
    if len(text) > 4096:
        raise HTTPException(status_code=400, detail="text is too long")

    limit = int(payload.limit or 10)
    matches = await container.rules_service.test_group_text_rules(group_id=gid, text=text, limit=limit)
    return {"group_id": gid, "matches": matches}


@app.post("/api/app/group/{group_id}/rules/create")
async def app_create_rule(group_id: int, payload: _RuleCreatePayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    action_params = {}
    if payload.action_type == "reply":
        action_params["text"] = str(payload.reply_text or "").strip()
        action_params["parse_mode"] = "Markdown"
        if not action_params["text"]:
            raise HTTPException(status_code=400, detail="reply_text is empty")
    if payload.action_type == "mute":
        action_params["duration_seconds"] = int(payload.mute_duration_seconds or 300)
    if payload.action_type == "log":
        txt = str(payload.log_text or "").strip()
        if txt:
            action_params["text"] = txt
    if payload.action_type == "start_sequence":
        seq_key = str(payload.sequence_key or "").strip()
        if not seq_key:
            raise HTTPException(status_code=400, detail="sequence_key is required")
        if len(seq_key) > 64:
            raise HTTPException(status_code=400, detail="sequence_key is too long")
        action_params["sequence_key"] = seq_key
        trig = str(payload.sequence_trigger_key or "").strip()
        if trig:
            if len(trig) > 64:
                raise HTTPException(status_code=400, detail="sequence_trigger_key is too long")
            action_params["trigger_key"] = trig
    if payload.action_type == "create_ticket":
        subj = str(payload.ticket_subject or "").strip()
        if subj:
            action_params["subject"] = subj

    try:
        rule_id = await container.rules_service.create_simple_rule(
            group_id=gid,
            created_by=user_id,
            name=str(payload.name or "Rule"),
            match_type=str(payload.match_type),
            pattern=str(payload.pattern),
            case_sensitive=bool(payload.case_sensitive),
            action_type=str(payload.action_type),
            action_params=action_params,
            priority=int(payload.priority or 100),
            stop_processing=bool(payload.stop_processing),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    rules = await container.rules_service.list_rules(gid)
    return {"group_id": gid, "rule_id": int(rule_id), "rules": rules}


@app.post("/api/app/group/{group_id}/rules/delete")
async def app_delete_rule(group_id: int, payload: _RuleDeletePayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    deleted = await container.rules_service.delete_rule(group_id=gid, rule_id=int(payload.rule_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="not found")

    rules = await container.rules_service.list_rules(gid)
    return {"group_id": gid, "rules": rules}


class _RuleTogglePayload(BaseModel):
    initData: str
    enabled: bool


@app.post("/api/app/group/{group_id}/rules/{rule_id}/delete")
async def app_delete_rule_by_id(group_id: int, rule_id: int, payload: _RuleTogglePayload):
    """Delete a rule by ID."""
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    deleted = await container.rules_service.delete_rule(group_id=gid, rule_id=int(rule_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="not found")

    rules = await container.rules_service.list_rules(gid)
    return {"group_id": gid, "rules": rules}


@app.post("/api/app/group/{group_id}/rules/{rule_id}/toggle")
async def app_toggle_rule(group_id: int, rule_id: int, payload: _RuleTogglePayload):
    """Toggle a rule's enabled status."""
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    try:
        await container.rules_service.toggle_rule(group_id=gid, rule_id=rule_id, enabled=payload.enabled)
        return {"success": True, "rule_id": rule_id, "enabled": payload.enabled}
    except Exception as e:
        logger.error(f"Failed to toggle rule {rule_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to toggle rule") from e


@app.post("/api/app/group/{group_id}/tickets")
async def app_list_tickets(group_id: int, payload: _TicketsListPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    # Get both open and closed tickets
    open_tickets = await container.ticket_service.list_tickets(group_id=gid, status="open", limit=50)
    closed_tickets = await container.ticket_service.list_tickets(group_id=gid, status="closed", limit=20)
    
    return {
        "group_id": gid,
        "tickets": open_tickets,
        "open_tickets": open_tickets,
        "closed_tickets": closed_tickets,
        "total_open": len(open_tickets),
        "total_closed": len(closed_tickets),
    }


class _TicketDetailPayload(BaseModel):
    initData: str


class _TicketReplyPayload(BaseModel):
    initData: str
    message: str


@app.post("/api/app/group/{group_id}/tickets/{ticket_id}")
async def app_get_ticket_detail(group_id: int, ticket_id: int, payload: _TicketDetailPayload):
    """Get ticket details and conversation history."""
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    # Get ticket info
    async with db.session() as session:
        from database.models import Ticket
        ticket = await session.get(Ticket, int(ticket_id))
        if not ticket or int(ticket.group_id) != gid:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        ticket_data = {
            "id": int(ticket.id),
            "group_id": int(ticket.group_id),
            "user_id": int(ticket.user_id),
            "status": str(ticket.status),
            "subject": str(ticket.subject or ""),
            "message": str(ticket.message or ""),
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
            "message_count": int(ticket.message_count or 1),
            "last_message_at": ticket.last_message_at.isoformat() if ticket.last_message_at else None,
        }

    # Get conversation history
    messages = await container.ticket_service.get_ticket_messages(ticket_id=ticket_id, limit=100)
    
    return {
        "ticket": ticket_data,
        "messages": messages,
    }


@app.post("/api/app/group/{group_id}/tickets/{ticket_id}/reply")
async def app_reply_to_ticket(group_id: int, ticket_id: int, payload: _TicketReplyPayload):
    """Send a reply to a ticket from the Mini App."""
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)
    admin_name = auth.user.get("first_name", "Admin")

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    message_text = (payload.message or "").strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(message_text) > 4000:
        raise HTTPException(status_code=400, detail="Message too long (max 4000 chars)")

    # Get ticket info
    async with db.session() as session:
        from database.models import Ticket
        ticket = await session.get(Ticket, int(ticket_id))
        if not ticket or int(ticket.group_id) != gid:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if str(ticket.status) != "open":
            raise HTTPException(status_code=400, detail="Cannot reply to a closed ticket")
        
        ticket_user_id = int(ticket.user_id)

    # Store the message
    await container.ticket_service.add_message(
        ticket_id=ticket_id,
        sender_type="staff",
        sender_id=user_id,
        sender_name=admin_name,
        message_type="text",
        content=message_text,
    )

    # Send to user
    bot = bot_obj.get_bot()
    try:
        await bot.send_message(
            chat_id=ticket_user_id,
            text=f"<b>Reply from support:</b>\n\n{message_text}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Failed to send ticket reply to user {ticket_user_id}: {e}")
        # Still return success since message was stored

    return {"ok": True, "ticket_id": ticket_id}


@app.post("/api/app/group/{group_id}/tickets/{ticket_id}/close")
async def app_close_ticket(group_id: int, ticket_id: int, payload: _TicketDetailPayload):
    """Close a ticket from the Mini App."""
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    # Verify ticket belongs to this group
    async with db.session() as session:
        from database.models import Ticket
        ticket = await session.get(Ticket, int(ticket_id))
        if not ticket or int(ticket.group_id) != gid:
            raise HTTPException(status_code=404, detail="Ticket not found")

    # Close the ticket
    await container.ticket_service.close_ticket(
        bot=bot_obj.get_bot(),
        ticket_id=ticket_id,
        closed_by_user_id=user_id,
        notify_user=True,
        close_topic=True,
    )

    return {"ok": True, "ticket_id": ticket_id, "status": "closed"}


@app.post("/api/app/group/{group_id}/analytics")
async def app_group_analytics(group_id: int, payload: _InitDataPayload):
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    gid = int(group_id)

    if not await can_user(bot_obj.get_bot(), gid, user_id, "settings"):
        raise HTTPException(status_code=403, detail="not allowed")

    from sqlalchemy import select, func
    from database.db import db
    from database.models import (
        Group,
        PendingJoinVerification,
        VerificationSession,
        Warning,
        AdminLog,
        FederationBan,
    )

    now = datetime.utcnow()
    since = now - timedelta(hours=24)

    async with db.session() as session:
        group = await session.get(Group, gid)

        pv_rows = await session.execute(
            select(PendingJoinVerification.status, func.count(PendingJoinVerification.id))
            .where(PendingJoinVerification.group_id == gid)
            .group_by(PendingJoinVerification.status)
        )
        pv_counts = {str(status): int(count) for status, count in pv_rows.all()}

        vs_rows = await session.execute(
            select(VerificationSession.status, func.count(VerificationSession.session_id))
            .where(VerificationSession.group_id == gid)
            .group_by(VerificationSession.status)
        )
        vs_counts = {str(status): int(count) for status, count in vs_rows.all()}

        warn_total = (
            await session.execute(select(func.count(Warning.id)).where(Warning.group_id == gid))
        ).scalar_one_or_none() or 0

        action_rows = await session.execute(
            select(AdminLog.action, func.count(AdminLog.id))
            .where(AdminLog.group_id == gid, AdminLog.timestamp >= since)
            .group_by(AdminLog.action)
        )
        actions_24h = {str(action): int(count) for action, count in action_rows.all()}

        fed_id = int(getattr(group, "federation_id", 0) or 0) if group else 0
        fed_bans = 0
        if fed_id:
            fed_bans = (
                await session.execute(
                    select(func.count(FederationBan.id)).where(FederationBan.federation_id == fed_id)
                )
            ).scalar_one_or_none() or 0

    return {
        "group_id": gid,
        "group_name": getattr(group, "group_name", None) if group else None,
        "as_of": now.isoformat(),
        "pending_join_verifications": pv_counts,
        "verification_sessions": vs_counts,
        "warnings_total": int(warn_total),
        "admin_actions_24h": actions_24h,
        "federation_id": fed_id or None,
        "federation_bans": int(fed_bans),
    }


@app.post(config.webhook_path)
async def webhook_handler(request: Request):
    """
    Handle incoming webhook updates from Telegram.
    
    This is called by Telegram whenever there's a new message, command, or event.
    Security: Validates X-Telegram-Bot-Api-Secret-Token header if WEBHOOK_SECRET is configured.
    """
    # Validate webhook secret token if configured
    if config.webhook_secret:
        secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret_header != config.webhook_secret:
            logger.warning("⚠️ Rejected webhook request: invalid or missing secret token")
            return Response(status_code=401)
    
    try:
        update_data = await request.json()
        update = Update(**update_data)

        # Debug visibility: record that we received an update (without logging message contents).
        _log_update_summary(update)
        
        # Process update
        try:
            await telegram_bot.get_dispatcher().feed_update(
                telegram_bot.get_bot(),
                update
            )
        except TelegramAPIError as e:
            # Non-actionable for Telegram retries (chat not found, blocked, message not modified, etc).
            # Log + count it, but ack the update so Telegram doesn't retry forever.
            logger.warning("tg_update=%s dropped: %s", update.update_id, e)
            try:
                if telegram_bot and telegram_bot.get_container():
                    await telegram_bot.get_container().metrics_service.incr_api_error("telegram_api")
            except Exception:
                pass
            return Response(status_code=200)
        
        return Response(status_code=200)
        
    except Exception as e:
        logger.error(f"❌ Error processing webhook update: {e}", exc_info=True)
        try:
            if telegram_bot and telegram_bot.get_container():
                await telegram_bot.get_container().metrics_service.incr_api_error("webhook_update")
        except Exception:
            pass
        return Response(status_code=500)


@app.get("/verify")
async def verify_redirect(
    session_id: str | None = None,
    app_name: str | None = None,
    app_domain: str | None = None,
    base64_qr: str = ""
):
    """
    Serve the deep link redirect page.
    
    This page automatically redirects to the Mercle app with the verification data.
    """
    try:
        # Read the verify.html file
        with open("static/verify.html", "r") as f:
            html_content = f.read()
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error serving verify page: {e}")
        return HTMLResponse(
            content="""
            <html>
                <head><title>Error</title></head>
                <body>
                    <h1>Error loading verification page</h1>
                    <p>Please try again or contact support.</p>
                </body>
            </html>
            """,
            status_code=500
        )


@app.get("/health")
async def health_check(request: Request):
    """
    Health check endpoint.
    
    Returns the health status of the bot and its components.
    """
    try:
        running = bool(telegram_bot and telegram_bot.is_running())
        payload = {"status": "ok", "running": running, "version": "2.0.0"}
        if not running:
            payload["detail"] = "initializing"

        # Only include internal details if an admin token is configured + provided.
        if _is_admin_request(request) and telegram_bot and telegram_bot.get_container():
            from database.db import db

            payload["database_ok"] = await db.health_check()
        return payload
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


@app.get("/status")
async def status(request: Request):
    """
    Status endpoint with detailed information.
    
    Returns statistics and configuration details.
    """
    try:
        if not _is_admin_request(request):
            return Response(status_code=403)

        if telegram_bot and telegram_bot.is_running():
            container = telegram_bot.get_container()
            
            # Get some basic stats
            from database.db import db
            from database.models import User, VerificationSession
            from sqlalchemy import select, func
            admin_actions, verification_outcomes, api_errors, last_update_at = await container.metrics_service.snapshot()
            
            async with db.session() as session:
                # Count verified users
                user_count = await session.execute(select(func.count(User.telegram_id)))
                total_users = user_count.scalar()
                
                # Count active sessions
                session_count = await session.execute(
                    select(func.count(VerificationSession.session_id))
                    .where(VerificationSession.status == "pending")
                )
                active_sessions = session_count.scalar()
            
            return {
                "status": "running",
                "version": "2.0.0",
                "stats": {
                    "total_verified_users": total_users,
                    "active_verification_sessions": active_sessions,
                    "admin_actions": admin_actions,
                    "verification_outcomes": verification_outcomes,
                    "api_errors": api_errors,
                    "last_update_at": last_update_at.isoformat() if last_update_at else None,
                },
                "config": {
                    "verification_timeout_minutes": container.config.timeout_minutes,
                    "action_on_timeout": container.config.action_on_timeout,
                    "auto_delete_messages": container.config.auto_delete_verification_messages
                }
            }
        else:
            return {
                "status": "initializing",
                "message": "Bot is starting up..."
            }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {"status": "error", "error": str(e)}


@app.post("/api/app/delete-my-data")
async def app_delete_my_data(payload: _InitDataPayload):
    """Delete all user data from the database."""
    bot_obj, container = _require_container()
    try:
        auth = validate_webapp_init_data(payload.initData, bot_token=container.config.bot_token)
    except WebAppAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = int(auth.user["id"])
    
    try:
        from database.db import db
        async with db.session() as session:
            from sqlalchemy import delete
            from database.models import (
                User, VerificationSession, PendingJoinVerification,
                VerificationLinkToken, GroupMember, Warning, Permission,
                Whitelist, DmSubscriber, DmPanelState, TicketUserState,
                GroupWizardState, AdminLog, Ticket, TicketMessage
            )
            
            # Delete in order respecting foreign keys
            # Note: Using correct column names for each model
            await session.execute(delete(TicketMessage).where(TicketMessage.sender_id == user_id))
            await session.execute(delete(TicketUserState).where(TicketUserState.user_id == user_id))
            await session.execute(delete(Ticket).where(Ticket.user_id == user_id))
            await session.execute(delete(AdminLog).where(AdminLog.admin_id == user_id))
            # GroupWizardState has no user column - skip it
            await session.execute(delete(DmPanelState).where(DmPanelState.telegram_id == user_id))
            await session.execute(delete(DmSubscriber).where(DmSubscriber.telegram_id == user_id))
            await session.execute(delete(Whitelist).where(Whitelist.telegram_id == user_id))
            await session.execute(delete(Permission).where(Permission.telegram_id == user_id))
            await session.execute(delete(Warning).where(Warning.telegram_id == user_id))
            await session.execute(delete(GroupMember).where(GroupMember.telegram_id == user_id))
            await session.execute(delete(VerificationLinkToken).where(VerificationLinkToken.telegram_id == user_id))
            await session.execute(delete(PendingJoinVerification).where(PendingJoinVerification.telegram_id == user_id))
            await session.execute(delete(VerificationSession).where(VerificationSession.telegram_id == user_id))
            await session.execute(delete(User).where(User.telegram_id == user_id))
            
            await session.commit()
            logger.info(f"Deleted all data for user {user_id}")
            
        return {"success": True, "message": "All your data has been deleted"}
    except Exception as e:
        logger.error(f"Failed to delete data for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete data") from e


@app.get("/")
async def root():
    """
    Root endpoint with API information.
    Note: Webhook path is intentionally not exposed for security.
    """
    return {
        "name": "Telegram Verification Bot",
        "description": "Biometric verification bot powered by Mercle SDK",
        "version": "2.0.0",
        "status": "running" if telegram_bot and telegram_bot.is_running() else "initializing",
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "verify": "/verify",
            "app": "/app"
        },
        "documentation": {
            "commands": "/help",
            "support": "support@mercle.ai"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
