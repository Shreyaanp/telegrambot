"""Webhook server for production deployment - clean architecture."""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from aiogram.types import Update
from pydantic import BaseModel

from bot.main import TelegramBot
from bot.config import Config
from bot.utils.permissions import can_delete_messages, can_pin_messages, can_restrict_members, can_user, is_bot_admin
from bot.utils.webapp_auth import WebAppAuthError, validate_webapp_init_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
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

            # Avoid logging raw user text; log commands everywhere, and non-command only for private.
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

            if chat_type == "private":
                logger.info(
                    "tg_update=%s kind=%s chat=%s(private) from=%s text_len=%s",
                    update.update_id,
                    kind,
                    chat_id,
                    from_id,
                    len(text),
                )
                return

            return

        logger.info("tg_update=%s kind=%s", update.update_id, kind)
    except Exception:
        return


def _get_admin_token_from_request(request: Request) -> str | None:
    # Prefer Authorization: Bearer <token>, fallback to X-Admin-Token or ?token=
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        parts = auth.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    token = request.headers.get("x-admin-token") or request.headers.get("X-Admin-Token")
    if token:
        return token.strip()
    token = request.query_params.get("token")
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
        
        # Set webhook
        webhook_url = f"{config.webhook_url}{config.webhook_path}"
        await telegram_bot.get_bot().set_webhook(
            url=webhook_url,
            allowed_updates=telegram_bot.get_dispatcher().resolve_used_update_types()
        )
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
    antiflood_enabled: bool | None = None
    antiflood_limit: int | None = None
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
                allowed.append(
                    {
                        "group_id": gid,
                        "group_name": group.group_name,
                        "settings": {
                            "verification_enabled": bool(getattr(group, "verification_enabled", True)),
                            "verification_timeout": int(getattr(group, "verification_timeout", 300) or 300),
                            "action_on_timeout": "kick" if bool(getattr(group, "kick_unverified", False)) else "mute",
                            "join_gate_enabled": bool(getattr(group, "join_gate_enabled", False)),
                            "antiflood_enabled": bool(getattr(group, "antiflood_enabled", True)),
                            "antiflood_limit": int(getattr(group, "antiflood_limit", 10) or 10),
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

    return {"user": user, "groups": allowed}


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

    # Join gate guardrails: enabling requires join requests + invite users.
    if payload.join_gate_enabled is True:
        preflight = await _bot_preflight(bot_obj.get_bot(), gid)
        if not preflight.get("join_by_request", False):
            raise HTTPException(status_code=400, detail="join requests are disabled (join_by_request=false)")
        if not preflight.get("invite_ok", False):
            raise HTTPException(status_code=400, detail="bot is missing Invite Users permission")

    action_on_timeout = payload.action_on_timeout
    if action_on_timeout is not None and action_on_timeout not in ("kick", "mute"):
        raise HTTPException(status_code=400, detail="action_on_timeout must be kick|mute")

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
        antiflood_enabled=payload.antiflood_enabled,
        antiflood_limit=payload.antiflood_limit,
    )

    if payload.lock_links is not None or payload.lock_media is not None:
        await container.lock_service.set_lock(gid, lock_links=payload.lock_links, lock_media=payload.lock_media)

    group = await container.group_service.get_or_create_group(gid)
    preflight = await _bot_preflight(bot_obj.get_bot(), gid)

    return {
        "group_id": gid,
        "group_name": group.group_name,
        "settings": {
            "verification_enabled": bool(getattr(group, "verification_enabled", True)),
            "verification_timeout": int(getattr(group, "verification_timeout", 300) or 300),
            "action_on_timeout": "kick" if bool(getattr(group, "kick_unverified", False)) else "mute",
            "join_gate_enabled": bool(getattr(group, "join_gate_enabled", False)),
            "antiflood_enabled": bool(getattr(group, "antiflood_enabled", True)),
            "antiflood_limit": int(getattr(group, "antiflood_limit", 10) or 10),
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

    tickets = await container.ticket_service.list_tickets(group_id=gid, status=str(payload.status or "open"))
    return {"group_id": gid, "tickets": tickets}


@app.post(config.webhook_path)
async def webhook_handler(request: Request):
    """
    Handle incoming webhook updates from Telegram.
    
    This is called by Telegram whenever there's a new message, command, or event.
    """
    try:
        update_data = await request.json()
        update = Update(**update_data)

        # Debug visibility: record that we received an update (without logging message contents).
        _log_update_summary(update)
        
        # Process update
        await telegram_bot.get_dispatcher().feed_update(
            telegram_bot.get_bot(),
            update
        )
        
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


@app.get("/")
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "name": "Telegram Verification Bot",
        "description": "Biometric verification bot powered by Mercle SDK",
        "version": "2.0.0",
        "status": "running" if telegram_bot and telegram_bot.is_running() else "initializing",
        "endpoints": {
            "webhook": config.webhook_path,
            "health": "/health",
            "status": "/status",
            "verify": "/verify"
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
