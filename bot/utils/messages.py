"""Message templates for the bot."""
from typing import Optional


def welcome_message(username: Optional[str] = None) -> str:
    """Generate welcome message for new users."""
    name = f"@{username}" if username else "there"
    return f"""👋 Welcome {name}!

I'm a verification bot that uses Mercle's biometric authentication.

Type /verify to get started!"""


def verification_prompt_message(timeout_seconds: int = 120) -> str:
    """Generate verification prompt message."""
    minutes = timeout_seconds // 60
    return f"""🔐 **Verification Required**

Please verify with Mercle face verification:

**Steps:**
1️⃣ Open Mercle app (download if needed using buttons below)
2️⃣ Tap the **QR Scanner** icon
3️⃣ Scan this QR code

⏰ You have **{minutes} minutes** to verify."""


def verification_success_message(mercle_user_id: str) -> str:
    """Generate success message after verification."""
    return f"""✅ **Verified Successfully!**

Welcome! You're now authenticated.

Your unique Mercle ID: `{mercle_user_id[:16]}...`

You can now participate in the group!"""


def verification_timeout_message() -> str:
    """Generate timeout message."""
    return """⏰ **Verification Timed Out**

You're still muted. When you're ready, type /verify to try again.

Need help? Visit: https://mercle.ai"""


def verification_failed_message() -> str:
    """Generate failed verification message."""
    return """❌ **Verification Failed**

Something went wrong with the verification.

Please try again with /verify

Need help? Contact support."""


def already_verified_message() -> str:
    """Message for users who are already verified."""
    return """✅ **You're Already Verified!**

No need to verify again. You're all set!"""


def group_welcome_message(group_name: str, timeout_seconds: int = 30) -> str:
    """Welcome message for new group members."""
    return f"""👋 Welcome to **{group_name}**!

🔐 Please verify your identity to participate.

I've sent you a private message with verification instructions.

⏰ You have **{timeout_seconds} seconds** to verify."""


def verification_reminder_message() -> str:
    """Reminder message for unverified users."""
    return """⚠️ **Verification Reminder**

You haven't completed verification yet.

Type /verify when you're ready to verify your identity."""


def help_message() -> str:
    """Help message with all available commands."""
    return """🤖 **Mercle Verification Bot**

**Available Commands:**
/start - Start the bot
/verify - Verify your identity with Mercle
/status - Check your verification status
/help - Show this help message

**How It Works:**
1. Type /verify to start verification
2. Scan the QR code with Mercle app (or tap button on mobile)
3. Complete face verification
4. Get unrestricted access to groups!

**Support:**
Need help? Visit https://mercle.ai/support"""


def status_message(verified: bool, mercle_user_id: Optional[str] = None) -> str:
    """Generate status message."""
    if verified and mercle_user_id:
        return f"""✅ **Verification Status: Verified**

Mercle ID: `{mercle_user_id[:16]}...`
Status: Active"""
    else:
        return """❌ **Verification Status: Not Verified**

Type /verify to get verified."""

