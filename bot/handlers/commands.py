"""Command handlers for the bot - simplified and user-friendly."""
import logging
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.container import ServiceContainer
from bot.utils.messages import (
    welcome_message,
    already_verified_message,
    help_message,
    admin_help_message,
    status_message,
    active_session_message,
)

logger = logging.getLogger(__name__)

router = Router()


def create_command_handlers(container: ServiceContainer) -> Router:
    """
    Create command handlers with dependency injection.
    
    Args:
        container: Service container with all dependencies
        
    Returns:
        Router with registered handlers
    """
    router = Router()
    
    @router.message(CommandStart())
    async def cmd_start(message: Message):
        """
        Handle /start command.
        
        Shows welcome message and explains what the bot does.
        """
        user_id = message.from_user.id
        username = message.from_user.username
        logger.info(f"[CMD]/start chat={message.chat.id} from={user_id} (@{username})")
        # Handle payload for deep link (e.g., menu-<group_id>)
        payload = None
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            payload = parts[1].strip()
        if payload and payload.startswith("menu-"):
            try:
                target_group_id = int(payload.replace("menu-", ""))
            except ValueError:
                target_group_id = None
            await _show_menu_dm(message, container, target_group_id)
            return
        
        # Default welcome flow
        is_verified = await container.user_manager.is_verified(user_id)
        if is_verified:
            await message.answer(already_verified_message(), parse_mode="Markdown")
        else:
            await message.answer(welcome_message(username), parse_mode="Markdown")
    
    @router.message(Command("verify"))
    async def cmd_verify(message: Message):
        """
        Handle /verify command.
        
        Starts the verification process for the user.
        """
        user_id = message.from_user.id
        username = message.from_user.username
        chat_id = message.chat.id
        logger.info(f"[CMD]/verify chat={chat_id} from={user_id} (@{username})")
        
        logger.info(f"User {user_id} (@{username}) used /verify")
        
        # Check if already verified
        is_verified = await container.user_manager.is_verified(user_id)
        if is_verified:
            await message.answer(
                already_verified_message(),
                parse_mode="Markdown"
            )
            return
        
        # Check if there's already an active verification session
        active_session = await container.user_manager.get_active_session(user_id)
        if active_session:
            await message.answer(
                active_session_message(),
                parse_mode="Markdown"
            )
            return
        
        # Start verification
        success = await container.verification_service.start_verification(
            bot=message.bot,
            telegram_id=user_id,
            chat_id=chat_id,
            username=username
        )
        
        # Error message is sent by the service itself
        if success:
            logger.info(f"✅ Started verification for user {user_id}")
        else:
            logger.error(f"❌ Failed to start verification for user {user_id}")
    
    @router.callback_query(lambda c: c.data and c.data.startswith("help_cmd_"))
    async def help_callbacks(callback: CallbackQuery):
        """
        Handle inline help buttons that send commands immediately.
        """
        data = callback.data
        mapping = {
            "help_cmd_start": "/start",
            "help_cmd_verify": "/verify",
            "help_cmd_status": "/status",
            "help_cmd_help": "/help",
        }
        cmd = mapping.get(data)
        if cmd:
            # Answer the callback to avoid loading state
            await callback.answer()
            # Send the command text as a message in the same chat
            await callback.message.answer(cmd)
    
    @router.message(Command("status"))
    async def cmd_status(message: Message):
        """
        Handle /status command.
        
        Shows the user's current verification status.
        """
        user_id = message.from_user.id
        logger.info(f"[CMD]/status chat={message.chat.id} from={user_id}")
        
        logger.info(f"User {user_id} checked /status")
        
        # Get user verification status
        user = await container.user_manager.get_user(user_id)
        
        if user:
            msg = status_message(True, user.mercle_user_id)
        else:
            msg = status_message(False)
        
        await message.answer(msg, parse_mode="Markdown")
    
    @router.message(Command("help"))
    async def cmd_help(message: Message):
        """
        Handle /help command.
        
        Shows all available commands and features.
        """
        user_id = message.from_user.id
        logger.info(f"[CMD]/help chat={message.chat.id} from={user_id}")
        
        logger.info(f"User {user_id} used /help")
        keyboard = [
            [
                InlineKeyboardButton(text="🚀 Start", callback_data="help_cmd_start"),
                InlineKeyboardButton(text="✅ Verify", callback_data="help_cmd_verify"),
            ],
            [
                InlineKeyboardButton(text="ℹ️ Status", callback_data="help_cmd_status"),
                InlineKeyboardButton(text="📚 Help", callback_data="help_cmd_help"),
            ],
        ]
        await message.answer(
            help_message(),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    
    @router.message(Command("help_admin"))
    async def cmd_help_admin(message: Message):
        """Admin-focused help."""
        await message.answer(admin_help_message(), parse_mode="Markdown")

    @router.message(Command("menu"))
    async def cmd_menu(message: Message):
        """
        Admin menu / onboarding.
        In group: send DM deep link. In DM: show onboarding and CTA to add bot to group.
        """
        bot_info = await message.bot.get_me()
        bot_username = bot_info.username
        
        if message.chat.type in ["group", "supergroup"]:
            # Register group info
            await container.group_service.register_group(message.chat.id, message.chat.title)
            deep_link = f"https://t.me/{bot_username}?start=menu-{message.chat.id}"
            await message.reply(
                "🛠 Manage this group in DM.\nTap below to open settings.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="Open settings in DM", url=deep_link)]
                    ]
                )
            )
            return
        
        # DM flow
        await _show_menu_dm(message, container, target_group_id=None)
    
    return router


async def _show_menu_dm(message: Message, container: ServiceContainer, target_group_id: int | None):
    """
    Render DM menu for admin/onboarding.
    """
    user_id = message.from_user.id
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username
    
    # Require verification first
    is_verified = await container.user_manager.is_verified(user_id)
    if not is_verified:
        await message.answer(
            "✅ Please verify yourself first.\n\n"
            "Use `/verify` here in DM, then come back to `/menu`.",
            parse_mode="Markdown"
        )
        return
    
    # Attempt to list groups where user is admin (best effort)
    groups = await container.group_service.list_groups()
    admin_groups = []
    for g in groups:
        if target_group_id and g.group_id != target_group_id:
            # If targeting a specific group, skip others
            continue
        try:
            member = await message.bot.get_chat_member(g.group_id, user_id)
            if member.status in ["creator", "administrator"]:
                admin_groups.append(g)
        except Exception as e:
            logger.debug(f"Could not check admin status in group {g.group_id}: {e}")
    
    
    add_link = f"https://t.me/{bot_username}?startgroup=true"
    base_lines = [
        "🛠 **Admin Menu**",
        "",
        f"[Add to group]({add_link}) (make me admin: restrict/delete/pin).",
        "Then run `/menu` in the group once; manage settings below.",
        ""
    ]
    
    if admin_groups:
        base_lines.append("")
        base_lines.append("**Your groups (detected):**")
        buttons = []
        for g in admin_groups[:10]:
            deep_link = f"https://t.me/{bot_username}?start=menu-{g.group_id}"
            name = g.group_name or g.group_id
            buttons.append([InlineKeyboardButton(text=str(name), callback_data=f"menu:group:{g.group_id}")])
        await message.answer(
            "\n".join(base_lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        return
    else:
        base_lines.append("")
        base_lines.append("No admin groups detected yet. Add the bot to a group and make it admin, then run `/menu` in the group once.")
    
    await message.answer("\n".join(base_lines), parse_mode="Markdown")


def build_settings_keyboard(group_id: int, current):
    """Build inline keyboard for group settings toggles/presets."""
    # current: dict with settings
    rows = []
    rows.append([
        InlineKeyboardButton(
            text=f"Verification: {'On' if current.get('verification_enabled') else 'Off'}",
            callback_data=f"settings:{group_id}:toggle_verification"
        )
    ])
    rows.append([
        InlineKeyboardButton(text="Timeout 120s", callback_data=f"settings:{group_id}:timeout:120"),
        InlineKeyboardButton(text="300s", callback_data=f"settings:{group_id}:timeout:300"),
        InlineKeyboardButton(text="600s", callback_data=f"settings:{group_id}:timeout:600"),
    ])
    rows.append([
        InlineKeyboardButton(text=f"Action: {'Kick' if current.get('kick_unverified') else 'Mute'}", callback_data=f"settings:{group_id}:action")
    ])
    rows.append([
        InlineKeyboardButton(text=f"Antiflood: {'On' if current.get('antiflood_enabled') else 'Off'}", callback_data=f"settings:{group_id}:toggle_antiflood"),
        InlineKeyboardButton(text="Limit 10", callback_data=f"settings:{group_id}:antiflood:10"),
        InlineKeyboardButton(text="Limit 20", callback_data=f"settings:{group_id}:antiflood:20"),
    ])
    rows.append([
        InlineKeyboardButton(text=f"Welcome: {'On' if current.get('welcome_enabled') else 'Off'}", callback_data=f"settings:{group_id}:toggle_welcome")
    ])
    rows.append([
        InlineKeyboardButton(text="Refresh", callback_data=f"settings:{group_id}:refresh")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(lambda c: c.data and c.data.startswith("menu:group:"))
async def menu_group_select(callback: CallbackQuery, container: ServiceContainer):
    """Handle group selection from DM menu."""
    try:
        _, _, group_id_str = callback.data.split(":")
        group_id = int(group_id_str)
    except Exception:
        await callback.answer("Invalid group.", show_alert=True)
        return
    
    # Verify caller is admin in that group
    try:
        member = await callback.bot.get_chat_member(group_id, callback.from_user.id)
        if member.status not in ["creator", "administrator"]:
            await callback.answer("You are not an admin in that group.", show_alert=True)
            return
    except Exception:
        await callback.answer("Cannot access that group.", show_alert=True)
        return
    
    group = await container.group_service.get_or_create_group(group_id)
    current = {
        "verification_enabled": group.verification_enabled,
        "kick_unverified": group.kick_unverified,
        "antiflood_enabled": group.antiflood_enabled,
        "welcome_enabled": group.welcome_enabled,
    }
    text = (
        f"⚙️ Settings for `{group.group_name or group_id}` (`{group_id}`)\n"
        f"- Verification: {'On' if group.verification_enabled else 'Off'}\n"
        f"- Timeout: {group.verification_timeout}s\n"
        f"- Action on timeout: {'kick' if group.kick_unverified else 'mute'}\n"
        f"- Antiflood: {'On' if group.antiflood_enabled else 'Off'} (limit {group.antiflood_limit})\n"
        f"- Welcome: {'On' if group.welcome_enabled else 'Off'}\n"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=build_settings_keyboard(group_id, current)
    )


@router.callback_query(lambda c: c.data and c.data.startswith("settings:"))
async def settings_callback(callback: CallbackQuery, container: ServiceContainer):
    """
    Handle inline settings updates.
    Format examples:
    settings:<group_id>:toggle_verification
    settings:<group_id>:timeout:<seconds>
    settings:<group_id>:action
    settings:<group_id>:toggle_antiflood
    settings:<group_id>:antiflood:<limit>
    settings:<group_id>:toggle_welcome
    settings:<group_id>:refresh
    """
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid settings action", show_alert=True)
        return
    _, group_id_str, action, *rest = parts
    try:
        group_id = int(group_id_str)
    except ValueError:
        await callback.answer("Invalid group id", show_alert=True)
        return
    
    # Permission check: caller must be admin in group
    try:
        member = await callback.bot.get_chat_member(group_id, callback.from_user.id)
        if member.status not in ["creator", "administrator"]:
            await callback.answer("You are not an admin in that group.", show_alert=True)
            return
    except Exception:
        await callback.answer("Cannot access that group.", show_alert=True)
        return
    
    group = await container.group_service.get_or_create_group(group_id)
    
    if action == "toggle_verification":
        await container.group_service.update_setting(group_id, verification_enabled=not group.verification_enabled)
    elif action == "timeout" and rest:
        try:
            seconds = int(rest[0])
            await container.group_service.update_setting(group_id, verification_timeout=seconds)
        except ValueError:
            await callback.answer("Invalid timeout", show_alert=True)
            return
    elif action == "action":
        new_action = "mute" if group.kick_unverified else "kick"
        await container.group_service.update_setting(group_id, action_on_timeout=new_action)
    elif action == "toggle_antiflood":
        await container.group_service.update_setting(group_id, antiflood_enabled=not group.antiflood_enabled)
    elif action == "antiflood" and rest:
        try:
            limit = int(rest[0])
            await container.group_service.update_setting(group_id, antiflood_limit=limit, antiflood_enabled=True)
        except ValueError:
            await callback.answer("Invalid limit", show_alert=True)
            return
    elif action == "toggle_welcome":
        await container.group_service.update_setting(group_id, welcome_enabled=not group.welcome_enabled)
    elif action == "refresh":
        pass
    else:
        await callback.answer("Unknown action", show_alert=True)
        return
    
    # Refresh view
    updated = await container.group_service.get_or_create_group(group_id)
    current = {
        "verification_enabled": updated.verification_enabled,
        "kick_unverified": updated.kick_unverified,
        "antiflood_enabled": updated.antiflood_enabled,
        "welcome_enabled": updated.welcome_enabled,
    }
    text = (
        f"⚙️ Settings for `{updated.group_name or group_id}` (`{group_id}`)\n"
        f"- Verification: {'On' if updated.verification_enabled else 'Off'}\n"
        f"- Timeout: {updated.verification_timeout}s\n"
        f"- Action on timeout: {'kick' if updated.kick_unverified else 'mute'}\n"
        f"- Antiflood: {'On' if updated.antiflood_enabled else 'Off'} (limit {updated.antiflood_limit})\n"
        f"- Welcome: {'On' if updated.welcome_enabled else 'Off'}\n"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=build_settings_keyboard(group_id, current)
    )
    await callback.answer("Updated.")
