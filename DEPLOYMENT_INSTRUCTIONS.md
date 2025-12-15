# Deployment Instructions for UX Improvements

## ✅ What's Been Done

All 8 phases of UX improvements have been implemented and pushed to GitHub:

1. ✅ Verification location (group/dm/both)
2. ✅ Welcome/goodbye system with buttons
3. ✅ Message filters and locks
4. ✅ Notes/tags system
5. ✅ Better message formatting
6. ✅ Admin action logs
7. ✅ Custom button support
8. ✅ Enhanced settings menu

**Total:** 2,500+ lines of code, 5 new plugins, 12 total plugins

---

## 🚀 Deploy to Production

### Step 1: SSH to EC2

```bash
ssh -i "helperinstance.pem" ubuntu@ec2-54-173-40-200.compute-1.amazonaws.com
```

### Step 2: Pull Latest Changes

```bash
cd /home/ubuntu/telegrambot
git pull origin main
```

### Step 3: Run Migration (IMPORTANT!)

```bash
PYTHONPATH=/home/ubuntu/telegrambot python3 database/migrate_ux_improvements.py
```

This will:
- Add new columns to groups table
- Create 4 new tables (filters, locks, notes, admin_logs)
- Preserve all existing data

### Step 4: Restart Bot

```bash
sudo systemctl restart telegrambot
```

### Step 5: Verify Deployment

```bash
# Check service status
sudo systemctl status telegrambot

# Check health endpoint
curl https://telegram.mercle.ai/health

# Check status endpoint (should show 12 plugins)
curl https://telegram.mercle.ai/status
```

---

## 🧪 Testing New Features

### Test Verification Location

```
# In your test group:
/settings location dm
# Add a new member, verify they get DM

/settings location group
# Add a new member, verify in group chat
```

### Test Welcome Messages

```
/setwelcome Welcome {mention} to {group}! [Rules](https://example.com/rules)
# Add a new member, check welcome message
```

### Test Filters

```
/filter hello Hello! Welcome to our group!
# Type "hello" in chat, bot should respond
/filters
```

### Test Locks

```
/lock links
# Post a link, it should be deleted
/locks
/unlock links
```

### Test Notes

```
/save rules Please read our rules at example.com
/get rules
#rules
/notes
```

### Test Admin Logs

```
/vkick @user
/adminlog
# Should show the kick action
```

---

## 📊 Expected Status

After deployment, the bot should show:

```json
{
  "status": "healthy",
  "plugins_loaded": 12,
  "plugins": [
    "Verification",
    "Admin",
    "Warnings",
    "Whitelist",
    "Rules",
    "Stats",
    "AntiFlood",
    "Greetings",      ← NEW
    "Filters",        ← NEW
    "Locks",          ← NEW
    "Notes",          ← NEW
    "AdminLogs"       ← NEW
  ]
}
```

---

## 📖 Documentation

Full documentation available in:
- `UX_IMPROVEMENTS_COMPLETE.md` - Complete feature documentation
- `README.md` - Updated with new commands

---

## 🎯 New Commands Available

After deployment, these commands will be available:

**Verification:**
- `/settings location <group/dm/both>`

**Greetings:**
- `/setwelcome <message>`
- `/setgoodbye <message>`
- `/welcome` (test)
- `/goodbye <on/off>`

**Filters:**
- `/filter <keyword> <response>`
- `/filters`
- `/stop <keyword>`

**Locks:**
- `/lock <type>`
- `/unlock <type>`
- `/locks`

**Notes:**
- `/save <notename> <content>`
- `/get <notename>`
- `#notename`
- `/notes`
- `/clear <notename>`

**Admin Logs:**
- `/adminlog`

---

## ⚠️ Important Notes

1. **Migration is required** - Don't skip the migration step!
2. **Existing data is preserved** - All current users, groups, and settings will remain intact
3. **New tables are created** - filters, locks, notes, admin_logs
4. **12 plugins total** - Verify all 12 plugins load successfully
5. **Test in a test group first** - Before using in production groups

---

## 🆘 Troubleshooting

### Bot doesn't start after deployment

```bash
# Check logs
sudo journalctl -u telegrambot -f

# Check for import errors
cd /home/ubuntu/telegrambot
PYTHONPATH=/home/ubuntu/telegrambot python3 -c "from webhook_server import *"
```

### Migration fails

```bash
# Check database file permissions
ls -la /home/ubuntu/telegrambot/bot_db.sqlite*

# Try running migration again
PYTHONPATH=/home/ubuntu/telegrambot python3 database/migrate_ux_improvements.py
```

### Plugins not loading

```bash
# Check status endpoint
curl https://telegram.mercle.ai/status

# Check logs for plugin errors
sudo journalctl -u telegrambot -f | grep -i plugin
```

---

## ✅ Success Criteria

Deployment is successful when:

1. ✅ Bot service is running
2. ✅ Health endpoint returns healthy
3. ✅ Status shows 12 plugins loaded
4. ✅ New commands work in test group
5. ✅ No errors in logs

---

## 🎉 You're Done!

Once deployed, the bot will have Rose bot-level features and UX!

Enjoy the new features! 🚀
