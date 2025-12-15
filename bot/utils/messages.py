"""Message templates for the bot with improved formatting and UX."""
from typing import Optional


def welcome_message(username: Optional[str] = None) -> str:
    """Generate welcome message for new users."""
    name = f"@{username}" if username else "there"
    return f"""👋 **Welcome {name}!**

I'm a verification bot powered by **Mercle's biometric authentication**.

🔐 Secure face verification
⚡ Quick and easy
🌍 Works globally

**Get Started:**
Type /verify to verify your identity

**Need Help?**
Type /help for more information"""


def verification_prompt_message(timeout_seconds: int = 120, group_name: Optional[str] = None) -> str:
    """Generate verification prompt message."""
    minutes = timeout_seconds // 60
    
    location_text = f"Welcome to **{group_name}**! " if group_name else ""
    
    return f"""🔐 **Verification Required**

{location_text}To participate, please verify your identity with Mercle.

📱 **Mobile Users:** Tap the button below
💻 **Desktop Users:** Scan the QR code with Mercle app

⏰ **Time remaining:** {minutes} minute{'s' if minutes != 1 else ''}

Don't have the app? Download it using the buttons below."""


def verification_dm_notice_message(group_name: str) -> str:
    """Message sent in group when verification is in DM."""
    return f"""👋 **Welcome to {group_name}!**

🔐 Please check your **private messages** to verify your identity.

⏰ You have a few minutes to complete verification."""


def verification_in_progress_message() -> str:
    """Message shown while verification is being processed."""
    return """⏳ **Verifying your identity...**

Please wait while we process your verification."""


def verification_success_message(mercle_user_id: str, group_name: Optional[str] = None) -> str:
    """Generate success message after verification."""
    location_text = f"\n\nYou can now participate in **{group_name}**!" if group_name else ""
    
    return f"""✅ **Verification Successful!**

🎉 Welcome! You're now authenticated with Mercle.{location_text}

**Your Mercle ID:** `{mercle_user_id[:16]}...`

🔐 **Powered by Mercle** - Secure biometric verification

**Get the Mercle app:**"""


def verification_timeout_message(group_name: Optional[str] = None) -> str:
    """Generate timeout message."""
    action_text = f"You have been removed from **{group_name}**." if group_name else "You're still muted."
    
    return f"""⏰ **Verification Timed Out**

{action_text}

**What to do:**
• Type /verify to try again
• Make sure you have the Mercle app installed
• Complete verification within the time limit

**Need help?**
Visit: https://mercle.ai/support"""


def verification_failed_message(reason: Optional[str] = None) -> str:
    """Generate failed verification message."""
    reason_text = f"\n\n**Reason:** {reason}" if reason else ""
    
    return f"""❌ **Verification Failed**

Something went wrong with the verification.{reason_text}

**What to do:**
• Type /verify to try again
• Make sure you have the Mercle app installed
• Ensure good lighting for face scan
• Contact support if problem persists

**Need help?**
Visit: https://mercle.ai/support"""


def already_verified_message() -> str:
    """Message for users who are already verified."""
    return """✅ **You're Already Verified!**

No need to verify again. You're all set!

**Your Status:** Active ✅
**Access:** Full access to all groups"""


def group_welcome_message(
    group_name: str,
    timeout_seconds: int = 120,
    user_mention: Optional[str] = None
) -> str:
    """Welcome message for new group members."""
    minutes = timeout_seconds // 60
    mention = user_mention if user_mention else "Welcome"
    
    return f"""👋 {mention} to **{group_name}**!

🔐 To participate in this group, please verify your identity.

⏰ You have **{minutes} minute{'s' if minutes != 1 else ''}** to verify.

Check below for verification instructions."""


def verification_reminder_message() -> str:
    """Reminder message for unverified users."""
    return """⚠️ **Verification Reminder**

You haven't completed verification yet.

**To verify:**
Type /verify and follow the instructions

**Why verify?**
• Get full access to group features
• Prove you're a real person
• Secure and private"""


def help_message() -> str:
    """Help message with all available commands."""
    return """🤖 **Mercle Verification Bot**

**👤 User Commands:**
/start - Get started with the bot
/verify - Verify your identity
/status - Check verification status
/help - Show this help message
/rules - View group rules (in groups)

**👮 Admin Commands:**
/settings - Configure bot settings
/vkick @user - Kick user from group
/vban @user [reason] - Ban user from group
/vverify @user - Manually verify user
/warn @user [reason] - Warn user
/warnings @user - Show user warnings
/resetwarns @user - Clear user warnings
/whitelist - Manage whitelist
/setrules <text> - Set group rules
/stats - Show verification statistics

**📝 How It Works:**
1. Type /verify to start
2. Scan QR code or tap button
3. Complete face verification
4. Get instant access!

**💡 Features:**
• Biometric face verification
• Auto-verification on group join
• Admin moderation tools
• Per-group settings

**🆘 Need Help?**
Visit: https://mercle.ai/support
Contact: @support"""


def status_message(verified: bool, mercle_user_id: Optional[str] = None) -> str:
    """Generate status message."""
    if verified and mercle_user_id:
        return f"""✅ **Verification Status: Verified**

**Mercle ID:** `{mercle_user_id[:16]}...`
**Status:** Active ✅
**Access:** Full access to all groups

You're all set! No further action needed."""
    else:
        return """❌ **Verification Status: Not Verified**

**Status:** Unverified ❌
**Access:** Limited

**To get verified:**
Type /verify and follow the instructions

**Benefits of verification:**
• Full access to group features
• Participate in discussions
• Trusted member status"""


def admin_action_success(action: str, target: str, reason: Optional[str] = None) -> str:
    """Success message for admin actions."""
    reason_text = f"\n**Reason:** {reason}" if reason else ""
    
    action_emoji = {
        "kick": "🚪",
        "ban": "🚫",
        "warn": "⚠️",
        "verify": "✅",
        "mute": "🔇",
        "unmute": "🔊"
    }.get(action, "✅")
    
    return f"""{action_emoji} **Action Completed**

**Action:** {action.capitalize()}
**Target:** {target}{reason_text}

Action has been logged."""


def admin_action_failed(action: str, target: str, error: str) -> str:
    """Failure message for admin actions."""
    return f"""❌ **Action Failed**

**Action:** {action.capitalize()}
**Target:** {target}
**Error:** {error}

Please check permissions and try again."""


def settings_display(
    group_name: str,
    verification_enabled: bool,
    auto_verify: bool,
    timeout: int,
    kick_on_timeout: bool,
    verification_location: str,
    welcome_set: bool,
    goodbye_set: bool,
    rules_set: bool
) -> str:
    """Display current group settings."""
    return f"""⚙️ **Group Settings: {group_name}**

**🔐 Verification:**
├─ Enabled: {'✅ Yes' if verification_enabled else '❌ No'}
├─ Auto-verify on join: {'✅ Yes' if auto_verify else '❌ No'}
├─ Location: {verification_location.upper()}
├─ Timeout: {timeout}s ({timeout // 60}m)
└─ Kick on timeout: {'✅ Yes' if kick_on_timeout else '❌ No'}

**💬 Messages:**
├─ Welcome message: {'✅ Set' if welcome_set else '❌ Not set'}
├─ Goodbye message: {'✅ Set' if goodbye_set else '❌ Not set'}
└─ Rules: {'✅ Set' if rules_set else '❌ Not set'}

**📝 Usage:**
`/settings timeout <seconds>` - Set timeout
`/settings location <group/dm/both>` - Set verification location
`/settings autoverify <on/off>` - Toggle auto-verify
`/setwelcome <message>` - Set welcome message
`/setrules <text>` - Set rules"""


def permission_denied_message() -> str:
    """Message when user lacks permissions."""
    return """⚠️ **Permission Denied**

You don't have permission to use this command.

**This command is for:**
• Group administrators
• Bot moderators

Contact a group admin if you need help."""


def user_not_found_message() -> str:
    """Message when target user is not found."""
    return """❌ **User Not Found**

Could not find the specified user.

**How to use:**
• Reply to the user's message
• Use their user ID
• Mention them with @username

**Example:**
`/vkick @username`"""


def invalid_command_usage(command: str, usage: str) -> str:
    """Message for invalid command usage."""
    return f"""❌ **Invalid Command Usage**

**Command:** {command}
**Correct usage:** {usage}

**Example:**
Type `/help {command}` for more information"""
