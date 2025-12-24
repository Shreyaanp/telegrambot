"""Message templates for the bot with improved UX."""


def welcome_message(username: str = None) -> str:
    """Welcome message for /start command."""
    greeting = f"👋 Hey @{username}!" if username else "👋 Hey there!"
    
    return f"""{greeting}

I'm your **Telegram Verification Bot** powered by Mercle 🔐

**Why am I here?**
I help keep Telegram groups safe by verifying that members are real humans using quick biometric checks. No bots, no spam, just real people!

**Here's how it works:**
1️⃣ Join a protected group → I'll send you a verification request
2️⃣ Tap the button to open Mercle app
3️⃣ Do a quick 5-second face scan
4️⃣ Done! You're verified ✅

**Quick Commands:**
 `/verify` - Start or retry verification
 `/status` - Check if you're verified
 `/help` - See all commands

**Pro tip:** Verify once, access all protected groups! Your verification works everywhere.

Ready to get started? Type `/verify` 🚀"""


def already_verified_message() -> str:
    """Message when user is already verified."""
    return """✅ **You're all set!**

Good news! Your Mercle account is already linked to this Telegram account.

You can join any protected group without verifying again. Some groups may still show a verification prompt when you first join, but it'll be instant since you're already verified.

**Useful commands:**
 `/status` - View your verification details and expiry
 `/help` - See what else I can do

**Tip:** Your verification lasts 7 days, then you'll need a quick re-verify to stay active."""


def verification_prompt_message(timeout_seconds: int) -> str:
    """Prompt message for verification with QR code."""
    minutes = timeout_seconds // 60
    
    return f"""🔐 **Verify with Mercle**

Complete a quick verification in the Mercle app.

📱 Tap the button below (recommended) or scan the QR in Mercle.

⏱️ **Time limit: {minutes} minutes**"""


def verification_success_message(mercle_user_id: str, bot_username: str = None) -> str:
    """Success message after verification."""
    base_msg = f"""✅ **Verified!**

🆔 Verification ID: `{mercle_user_id}`

✨ You're all set! You can now:
• Return to any group you were trying to join
• Access all group features
• Use the Mini App to manage your groups"""
    
    # Add Mini App return button if bot username is available
    if bot_username:
        base_msg += f"\n\n👉 [Return to Mini App](https://t.me/{bot_username}/app)"
    
    return base_msg


def verification_failed_message() -> str:
    """Message when verification fails."""
    return """❌ **Verification Didn't Go Through**

The verification was rejected or cancelled. Don't worry, this happens sometimes!

**Common fixes:**
 💡 Find better lighting (face needs to be clearly visible)
 📱 Make sure you're using the latest Mercle app
 👤 Remove glasses/hats if they're blocking your face
 🔄 Try `/verify` again when you're ready

**Still stuck?**
• Check if Mercle app has camera permissions
• Contact group admins for help
• Reach out to Mercle support: support@mercle.ai

You've got this! 💪"""


def verification_timeout_message() -> str:
    """Message when verification times out."""
    return """⏰ **Verification Timed Out**

You didn’t complete verification in time.

Try again with `/verify` when you’re ready."""


def group_welcome_message(group_name: str, timeout_seconds: int) -> str:
    """Welcome message sent in the group when someone joins."""
    minutes = timeout_seconds // 60
    
    return f"""👋 **Welcome to {group_name}!**

🔐 This group uses **biometric verification** to keep out bots and ensure everyone here is a real person.

**Quick action needed:**
1. 📬 Check your **DM from me** (the bot)
2. 👆 Tap the verification button
3. 📱 Complete a 5-second face scan in Mercle app
4. ✅ Done! You'll be able to chat immediately

⏱️ **Time limit: {minutes} minutes** (or you'll be auto-removed)

**First time?** No worries! The whole process takes under 30 seconds. If you've verified before, it's even faster! 🚀"""


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
- Use the Mini App to manage all bot settings.
- Configure verification, timeout, action (kick/mute), antiflood, and welcome messages.

Need more? Contact your group admins."""


def status_message(is_verified: bool, mercle_user_id: str = None) -> str:
    """Status message showing verification status."""
    if is_verified:
        return f"""✅ **Verification Status: ACTIVE**

🆔 **Your ID:** `{mercle_user_id}`

**You're all set!** Here's what you can do:
 ✨ Join any protected group instantly
 🌍 Your verification works globally (all groups)
 🔄 Valid for 7 days, then quick re-verify needed

**Pro tip:** Use the Mini App to manage your groups and see when your verification expires.

**Commands:**
 `/help` - See what else I can do"""
    else:
        return """❌ **Verification Status: NOT VERIFIED**

You haven't completed biometric verification yet. Let's fix that!

**Getting verified is easy:**
1. Type `/verify` below
2. Tap the button I send you
3. Do a quick 5-second face scan
4. You're done! ✅

**Why bother?**
 🚪 Access to protected Telegram groups
 🤖 Prove you're a real human (no bots allowed!)
 🌍 Verify once, use everywhere (global verification)

**Takes 30 seconds, lasts 7 days.** Ready? Type `/verify` now! 🚀"""


def active_session_message() -> str:
    """Message when user already has an active session."""
    return """⏳ **Hold on! You've already started verification**

You have an active verification session running right now.

**What to do:**
 📜 Scroll up to find your previous verification message
 ✅ Complete that verification first
 ⏰ Or wait a few minutes for it to expire, then try again

**Tip:** Only one verification can run at a time to prevent confusion.

**Still stuck?** Contact the group admins for help."""


def verification_error_message() -> str:
    """Generic error message for verification failures."""
    return """❌ **Oops! Something went wrong**

I couldn't start your verification right now. This is usually temporary!

**Quick fixes:**
 ⏱️ Wait 10-30 seconds and try `/verify` again
 📶 Check your internet connection
 🔄 Restart the Mercle app if it's acting up

**Still not working?**
 • Contact the group admins
 • Check if Mercle servers are up
 • Try again in a few minutes

**Technical note:** This might be a temporary glitch with the verification service. Usually resolves itself quickly! 🔧"""
