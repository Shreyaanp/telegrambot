"""Message templates for the bot with improved UX."""


def welcome_message(username: str = None) -> str:
    """Welcome message for /start command."""
    greeting = f"👋 Welcome, @{username}!" if username else "👋 Welcome!"
    
    return f"""{greeting}

🔐 **Telegram Verification Bot**

This bot uses **biometric verification** powered by Mercle to ensure all group members are real humans.

**How it works:**
1️⃣ When you join a group, you'll be asked to verify
2️⃣ Tap the button to open the Mercle app
3️⃣ Complete a quick face scan (takes 5 seconds)
4️⃣ You're verified! ✅

**Commands:**
 `/verify` - Start verification
 `/status` - Check your verification status
 `/help` - Show all commands

**Need the Mercle app?**
It's free and takes 30 seconds to set up!

Let's get you verified! 🚀"""


def already_verified_message() -> str:
    """Message when user is already verified."""
    return """✅ **You're already verified!**

You can join any group protected by this bot without needing to verify again.

Your verification is permanent and works across all groups.

**Commands:**
 `/status` - View your verification details
 `/help` - See all available commands"""


def verification_prompt_message(timeout_seconds: int) -> str:
    """Prompt message for verification with QR code."""
    minutes = timeout_seconds // 60
    
    return f"""🔐 **Verify Your Identity**

Please complete biometric verification to access this group.

**Two ways to verify:**

📱 **Option 1: Tap the button below**
The easiest way! It will open the Mercle app automatically.

📷 **Option 2: Scan the QR code**
Open the Mercle app and scan this QR code.

⏱️ **You have {minutes} minutes to complete verification.**

**Don't have the Mercle app?**
Download it using the buttons below (it's free and takes 30 seconds!)"""


def verification_success_message(mercle_user_id: str) -> str:
    """Success message after verification."""
    return f"""✅ **Verification Successful!**

Welcome! You've been verified and can now participate in the group.

🆔 Your Verification ID: `{mercle_user_id}`

**What now?**
 You can chat freely in the group
 Your verification works across all groups using this bot
 You won't need to verify again

**Love Mercle?**
Download the full app to explore more features! 👇"""


def verification_failed_message() -> str:
    """Message when verification fails."""
    return """❌ **Verification Failed**

The verification was rejected or cancelled.

**What to do:**
 Try again with `/verify`
 Make sure you're in a well-lit area
 Follow the instructions in the Mercle app carefully

**Need help?**
Contact the group admins or Mercle support."""


def verification_timeout_message() -> str:
    """Message when verification times out."""
    return """⏰ **Verification Timed Out**

You didn't complete verification in time.

**What happens now:**
 You've been removed from the group
 You can rejoin and try again
 Make sure to complete verification quickly next time

**Tips for faster verification:**
1. Have the Mercle app installed before joining
2. Be in a well-lit area
3. Follow the prompts immediately"""


def group_welcome_message(group_name: str, timeout_seconds: int) -> str:
    """Welcome message sent in the group when someone joins."""
    minutes = timeout_seconds // 60
    
    return f"""👋 **Welcome to {group_name}!**

🔐 This group requires **biometric verification** to ensure all members are real humans.

**What you need to do:**
1. Check your **private messages** from me
2. Follow the verification instructions
3. Complete the quick face scan

⏱️ You have **{minutes} minutes** to verify, or you'll be removed.

**First time?** Don't worry! It takes less than 30 seconds. 🚀"""


def help_message() -> str:
    """Help message with all commands."""
    return """📚 **Telegram Verification Bot - Help**

**User Commands:**
/start  – Start the bot and see welcome
/verify – Start or restart verification
/status – Check your verification status
/help   – Show this help

**Admin Commands:**
/settings              – View/change group settings
/vverify @user         – Manually verify a user (bypass biometrics)
/vunverify @user       – Remove user's verification
/kick @user            – Kick user
/ban @user [reason]    – Ban user
/unban @user           – Unban user
/mute @user            – Mute user
/unmute @user          – Unmute user
/warn @user [reason]   – Warn user
/warns @user           – Check warnings
/resetwarns @user      – Reset warnings
/whitelist             – Manage whitelist
/rules                 – Show group rules
/setrules <text>       – Set group rules
/stats                 – Show verification stats

**About Verification:**
This bot uses Mercle's biometric verification to ensure all group members are real humans. Verification is:
✅ Fast (takes ~30 seconds)
✅ Secure (biometric data stays on device)
✅ Global (verify once, access all groups)

**Need Support?**
Bot issues: contact group admins
Mercle app: support@mercle.ai
Website: https://mercle.ai"""


def admin_help_message() -> str:
    """Admin help with guidance on targets/permissions."""
    return """🛠 **Admin Help**

**Moderation (reply-first):**
/kick, /ban, /mute, /warn, /resetwarns work best when you **reply** to the user's message. This avoids @username lookup limits.

**Inline actions:**
Reply to a user and send `/actions` to get buttons (Kick/Ban/Tempban/Mute/Unmute/Warn). Buttons operate on the replied user.

**User targeting limits:**
- Telegram does **not** guarantee resolving arbitrary @usernames to IDs.
- If not replying, use numeric IDs: `/kick <user_id> [reason]`.
- Inline buttons are the most reliable way to target.

**Bot permissions:**
- Make the bot an **Admin**.
- Grant **Restrict Members** and **Delete Messages** (Pin optional).

**Settings:**
- Use `/menu` in the group to open DM settings.
- In DM `/menu`, pick your group to toggle verification, timeout, action (kick/mute), antiflood, and welcome.

Need more? Contact your group admins."""


def status_message(is_verified: bool, mercle_user_id: str = None) -> str:
    """Status message showing verification status."""
    if is_verified:
        return f"""✅ **Verification Status: VERIFIED**

🆔 **Verification ID:** `{mercle_user_id}`

**What this means:**
 You can join and participate in any group using this bot
 Your verification is permanent and global
 No need to verify again

**Commands:**
 `/help` - See all available commands"""
    else:
        return """❌ **Verification Status: NOT VERIFIED**

You haven't completed biometric verification yet.

**To get verified:**
1. Use the `/verify` command
2. Follow the instructions
3. Complete the quick face scan

**Why verify?**
 Access protected groups
 Prove you're a real human
 One-time process (verify once, use everywhere)

**Ready?** Type `/verify` to start! 🚀"""


def active_session_message() -> str:
    """Message when user already has an active session."""
    return """⏳ **Verification In Progress**

You already have an active verification session.

**What to do:**
 Check your previous verification message
 Complete the verification there
 Wait for it to expire if you want to start over

**Need help?**
Contact the group admins if you're stuck."""


def verification_error_message() -> str:
    """Generic error message for verification failures."""
    return """❌ **Verification Error**

Something went wrong while starting verification.

**What to do:**
 Wait a moment and try `/verify` again
 Check your internet connection
 Contact group admins if the problem persists

**Technical Issue?**
This might be a temporary problem with the verification service."""
