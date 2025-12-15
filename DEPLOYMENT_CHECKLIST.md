# 🚀 Deployment Checklist - Rose-Style Bot

## ✅ Pre-Deployment Checklist

### 1. Code Review
- [x] All 9 phases implemented
- [x] Database schema created (8 tables)
- [x] All plugins created (7 plugins)
- [x] Services layer complete (5 services)
- [x] Webhook server updated
- [x] Documentation complete

### 2. Environment Setup
- [ ] Verify `.env` file has all required variables:
  ```bash
  cat .env | grep -E "BOT_TOKEN|MERCLE_API|WEBHOOK"
  ```
- [ ] Ensure webhook path is secure (random string)
- [ ] Verify domain points to EC2 instance
- [ ] SSL certificate is valid

### 3. Dependencies
- [ ] Install/update requirements:
  ```bash
  source venv/bin/activate
  pip install -r requirements.txt
  ```

## 🧪 Testing Checklist

### Local Testing (Optional)
```bash
# Test database initialization
python3 << 'EOF'
import asyncio
from database import init_database

async def test():
    db = await init_database()
    print("✅ Database OK")
    counts = await db.get_table_counts()
    print(f"Tables: {counts}")
    await db.disconnect()

asyncio.run(test())
EOF
```

### Production Deployment

#### Step 1: Backup Current State
```bash
ssh -i ~/.ssh/helperinstance.pem ubuntu@ec2-54-173-40-200.compute-1.amazonaws.com << 'EOF'
cd /home/ubuntu/telegrambot
cp bot_db.sqlite bot_db.backup.$(date +%Y%m%d_%H%M%S).sqlite
echo "✅ Backup created"
EOF
```

#### Step 2: Deploy New Code
```bash
# Push code to Git
git add .
git commit -m "Rose-style bot rewrite - complete implementation"
git push origin main

# Pull on EC2
ssh -i ~/.ssh/helperinstance.pem ubuntu@ec2-54-173-40-200.compute-1.amazonaws.com << 'EOF'
cd /home/ubuntu/telegrambot
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
echo "✅ Code deployed"
EOF
```

#### Step 3: Restart Service
```bash
ssh -i ~/.ssh/helperinstance.pem ubuntu@ec2-54-173-40-200.compute-1.amazonaws.com << 'EOF'
sudo systemctl restart telegrambot
sleep 5
sudo systemctl status telegrambot --no-pager
echo "✅ Service restarted"
EOF
```

#### Step 4: Verify Health
```bash
# Check health endpoint
curl -s https://telegram.mercle.ai/health | jq

# Check status endpoint
curl -s https://telegram.mercle.ai/status | jq

# Check webhook is set
# (Should see "Webhook set to: https://telegram.mercle.ai/webhook/...")
```

#### Step 5: Monitor Logs
```bash
ssh -i ~/.ssh/helperinstance.pem ubuntu@ec2-54-173-40-200.compute-1.amazonaws.com
sudo journalctl -u telegrambot -f
```

## 🎮 Functional Testing

### Test 1: Auto-Verification on Group Join
- [ ] Create a new Telegram group
- [ ] Add bot to group
- [ ] Make bot admin with:
  - [ ] Delete messages permission
  - [ ] Ban users permission
  - [ ] Restrict members permission
- [ ] Join group with test account
- [ ] Verify user is muted
- [ ] Verify QR code + buttons appear in group
- [ ] Complete verification in Mercle app
- [ ] Verify user is unmuted
- [ ] Verify messages are deleted
- [ ] Verify success message shows

### Test 2: Manual /verify Command
- [ ] Send `/start` to bot in DM
- [ ] Send `/verify` to bot in DM
- [ ] Complete verification
- [ ] Verify success message

### Test 3: Admin Commands
- [ ] `/settings` - View current settings
- [ ] `/settings timeout 180` - Update timeout
- [ ] `/settings autoverify on` - Enable auto-verify
- [ ] `/vverify @user` - Manually verify user
- [ ] `/vkick @user` - Kick user
- [ ] `/vban @user spam` - Ban user

### Test 4: Warning System
- [ ] `/warn @user reason` - Add warning
- [ ] `/warnings @user` - Show warnings
- [ ] Add 3 warnings - Verify auto-kick
- [ ] `/resetwarns @user` - Clear warnings

### Test 5: Whitelist
- [ ] `/whitelist add @user` - Add to whitelist
- [ ] `/whitelist list` - Show whitelisted users
- [ ] Verify whitelisted user skips verification
- [ ] `/whitelist remove @user` - Remove from whitelist

### Test 6: Rules & Stats
- [ ] `/setrules Group rules here` - Set rules
- [ ] `/rules` - Display rules
- [ ] `/stats` - Show statistics

### Test 7: Anti-Flood
- [ ] Send 15+ messages rapidly
- [ ] Verify auto-mute for 5 minutes

### Test 8: Timeout Behavior
- [ ] Join group and don't verify
- [ ] Wait for timeout (2 minutes default)
- [ ] Verify user is kicked
- [ ] Verify messages are cleaned up

### Test 9: Whitelisted User Flow
- [ ] Add user to whitelist
- [ ] User joins group
- [ ] Verify user is NOT muted
- [ ] Verify no verification required

### Test 10: Already Verified User
- [ ] User verified in one group
- [ ] User joins another group
- [ ] Verify immediate access (no verification)
- [ ] Verify welcome back message

## 📊 Monitoring Checklist

### Health Checks
- [ ] Set up monitoring for `/health` endpoint
- [ ] Set up alerts for service downtime
- [ ] Monitor database file size
- [ ] Track verification success rate

### Log Monitoring
```bash
# Watch for errors
sudo journalctl -u telegrambot -f | grep -i error

# Watch verification completions
sudo journalctl -u telegrambot -f | grep -i "verification successful"

# Watch plugin loading
sudo journalctl -u telegrambot -f | grep -i "plugin loaded"
```

### Database Monitoring
```bash
# Check database size
ls -lh bot_db.sqlite

# Check table counts
curl -s https://telegram.mercle.ai/status | jq .database
```

## 🔧 Troubleshooting

### Bot Not Starting
1. Check logs: `sudo journalctl -u telegrambot -xe`
2. Verify `.env` file exists and has correct values
3. Check Python version: `python3 --version` (should be 3.11+)
4. Verify dependencies: `pip list | grep aiogram`

### Webhook Not Working
1. Verify webhook URL is accessible: `curl https://telegram.mercle.ai/health`
2. Check Telegram webhook status: Check logs for "Webhook set to..."
3. Verify SSL certificate is valid
4. Check Nginx configuration

### Database Errors
1. Check database file permissions: `ls -l bot_db.sqlite`
2. Verify WAL mode is enabled: `sqlite3 bot_db.sqlite "PRAGMA journal_mode;"`
3. Check disk space: `df -h`

### Plugin Not Loading
1. Check logs for plugin load errors
2. Verify plugin file exists
3. Check for syntax errors: `python3 -m py_compile bot/plugins/plugin_name.py`

## 📞 Rollback Plan

If something goes wrong:

```bash
# Stop the service
sudo systemctl stop telegrambot

# Restore backup database
cp bot_db.backup.TIMESTAMP.sqlite bot_db.sqlite

# Restore old code
git checkout previous-commit-hash

# Restart service
sudo systemctl start telegrambot
```

## ✅ Post-Deployment Verification

### Success Criteria
- [ ] Bot responds to commands
- [ ] Health endpoint returns healthy
- [ ] Status endpoint shows all plugins loaded
- [ ] New members can join and verify
- [ ] Admin commands work
- [ ] No errors in logs for 1 hour
- [ ] Database is being updated correctly

### Performance Metrics
- [ ] Average verification time: < 30 seconds
- [ ] Message cleanup: < 1 second
- [ ] Command response time: < 500ms
- [ ] Memory usage: < 500MB
- [ ] CPU usage: < 10% idle

## 🎉 Deployment Complete!

Once all checklist items are verified:
- [ ] Bot is running in production
- [ ] All features tested and working
- [ ] Monitoring is set up
- [ ] Documentation is up to date
- [ ] Team is notified

---

**Date Deployed:** _____________
**Deployed By:** _____________
**Version:** 2.0.0 (Rose-Style Rewrite)
**Status:** ✅ PRODUCTION READY

