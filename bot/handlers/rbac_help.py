"""Role-aware help and command discovery (since Telegram slash menu isn't per-role)."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.container import ServiceContainer
from bot.utils.permissions import has_role_permission, is_user_admin


def create_rbac_help_handlers(container: ServiceContainer) -> Router:
    router = Router()

    @router.message(Command("mycommands"))
    async def cmd_mycommands(message: Message):
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply("Run /mycommands in a group.", parse_mode="HTML")
            return

        gid = message.chat.id
        uid = message.from_user.id
        is_admin = await is_user_admin(message.bot, gid, uid)

        allowed = []
        # Always useful
        allowed.append("/rules")
        allowed.append("/report (reply)")
        allowed.append("/ticket")

        # Moderation panel (shown only if you can use it).
        if is_admin or any(
            [
                await has_role_permission(gid, uid, "warn"),
                await has_role_permission(gid, uid, "kick"),
                await has_role_permission(gid, uid, "ban"),
            ]
        ):
            allowed.append("/actions (reply)")

        if is_admin or await has_role_permission(gid, uid, "settings"):
            allowed.append("/menu")
            allowed.append("/checkperms")
            allowed.append("/raid [minutes|off]")
            allowed.append("/fed")
        if is_admin or await has_role_permission(gid, uid, "status"):
            allowed.append("/status")
        if is_admin or await has_role_permission(gid, uid, "logs"):
            allowed.append("/modlog")
        if is_admin or await has_role_permission(gid, uid, "warn"):
            allowed.append("/warn (reply)")
        if is_admin or await has_role_permission(gid, uid, "kick"):
            allowed.append("/kick (reply)")
            allowed.append("/mute (reply)")
            allowed.append("/unmute (reply)")
        if is_admin or await has_role_permission(gid, uid, "ban"):
            allowed.append("/ban (reply)")
            allowed.append("/unban <user_id>")
            allowed.append("/fban (reply)")
            allowed.append("/funban <user_id>")
        if is_admin or await has_role_permission(gid, uid, "verify"):
            allowed.append("/whitelist")
        if is_admin or await has_role_permission(gid, uid, "locks"):
            allowed.append("/lock links|media|all")
            allowed.append("/unlock links|media|all")
        if is_admin:
            allowed.append("/roles")

        text = (
            "<b>Your commands</b>\n"
            + "\n".join(f"• {cmd}" for cmd in allowed)
            + "\n\n<i>Note:</i> Telegram’s “/” menu can’t be customized per custom role.\n"
            "If you have a role, type the command manually (or run <code>/actions</code> on a reply)."
        )
        await message.reply(text, parse_mode="HTML")

    return router
