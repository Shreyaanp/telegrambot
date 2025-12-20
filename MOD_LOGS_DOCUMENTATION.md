# Mod Logs System Documentation
**Last Updated:** 2024-12-20  
**Status:** ✅ COMPLETE

## Overview
The mod logs system tracks all administrative actions in Telegram groups and optionally sends real-time notifications to a designated logs channel/group.

---

## Architecture

### Components

1. **AdminLog Model** (`database/models.py`)
   - Stores all admin actions in the database
   - Fields: `id`, `group_id`, `admin_id`, `target_id`, `action`, `reason`, `timestamp`
   - Indexed for fast queries by group, admin, target, and time

2. **LogsService** (`bot/services/logs_service.py`)
   - Query interface for retrieving logs
   - Methods: `get_recent_logs()`, `get_logs_by_admin()`, `get_logs_by_target()`

3. **AdminService** (`bot/services/admin_service.py`)
   - Creates log entries when actions are performed
   - Sends notifications to logs channel if configured
   - Method: `log_custom_action(bot, group_id, actor_id, target_id, action, reason)`

---

## How It Works

### 1. Action Execution
When an admin performs an action (kick, ban, warn, etc.):

```python
# Example: Kicking a user
await admin_service.kick_user(
    bot=bot,
    group_id=group_id,
    user_id=user_id,
    admin_id=admin_id,
    reason="Spam"
)
```

### 2. Log Creation
The action automatically creates a log entry:

```python
# Inside admin_service methods
log = AdminLog(
    group_id=group_id,
    admin_id=admin_id,
    target_id=user_id,
    action="kick",
    reason=reason,
    timestamp=datetime.utcnow()
)
session.add(log)
```

### 3. Notification (Optional)
If logs are enabled for the group, a message is sent to the logs channel:

```python
# Check if logs are enabled
if group.logs_enabled and group.logs_chat_id:
    await bot.send_message(
        chat_id=group.logs_chat_id,
        text=log_message,
        message_thread_id=group.logs_thread_id  # Optional: for forum topics
    )
```

---

## Configuration

### Database Settings (Group Model)
```python
logs_enabled: bool = False          # Enable/disable log notifications
logs_chat_id: int | None = None     # Destination chat ID
logs_thread_id: int | None = None   # Optional: forum topic thread ID
```

### Configuring via Mini App

1. **Open Settings** → Navigate to group settings in Mini App
2. **Enable Logs** → Toggle "Enable Logs" switch
3. **Set Destination** → Enter logs channel/group ID
4. **Test** → Click "Test Logs" button to verify

**Location in Code:** `static/app.html` (Settings view, lines ~2030-2050)

### Configuring via Bot Commands

Currently, logs are configured through the Mini App only. Bot commands for logs configuration are not implemented.

---

## Logged Actions

### User Moderation
- `kick` - User kicked from group
- `ban` - User banned from group
- `unban` - User unbanned
- `mute` - User muted (restricted)
- `unmute` - User unmuted
- `warn` - User warned
- `reset_warns` - User warnings reset

### Verification
- `manual_verify` - Admin manually verified user
- `manual_unverify` - Admin removed user's verification

### Automated Actions
- `raid_kick` - User kicked during raid mode
- `block_no_username` - User kicked for no username
- `antiflood_mute` - User muted for flooding
- `antiflood_kick` - User kicked for flooding
- `antiflood_ban` - User banned for flooding

### Rules Engine
- `rule_log` - Rule matched and logged

### Custom Actions
- Any action can be logged with `log_custom_action()`

---

## Log Message Format

### Standard Format
```
🔨 Action: kick
👤 Target: @username (ID: 123456789)
👮 Admin: @admin_username (ID: 987654321)
📝 Reason: Spam
⏰ Time: 2024-12-20 14:30:00 UTC
```

### Automated Actions
```
🤖 Automated Action: raid_kick
👤 Target: @username (ID: 123456789)
📝 Reason: Raid mode active: blocked new join
⏰ Time: 2024-12-20 14:30:00 UTC
```

---

## API Endpoints

### Test Logs Destination
**POST** `/api/app/group/{group_id}/logs/test`

Tests if the bot can send messages to the configured logs channel.

**Request:**
```json
{
  "initData": "telegram_web_app_init_data"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Test message sent successfully"
}
```

### Update Logs Configuration
**POST** `/api/app/group/{group_id}/settings`

Updates group settings including logs configuration.

**Request:**
```json
{
  "initData": "telegram_web_app_init_data",
  "logs_mode": "group",  // "off" or "group"
  // ... other settings
}
```

---

## Database Schema

### AdminLog Table
```sql
CREATE TABLE admin_logs (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL,
    admin_id BIGINT NOT NULL,
    target_id BIGINT,
    action VARCHAR NOT NULL,
    reason TEXT,
    timestamp TIMESTAMP NOT NULL,
    
    FOREIGN KEY (group_id) REFERENCES groups(group_id)
);

CREATE INDEX idx_admin_logs ON admin_logs(group_id, timestamp);
CREATE INDEX idx_target_logs ON admin_logs(group_id, target_id);
```

---

## Best Practices

### For Admins

1. **Set up a dedicated logs channel**
   - Create a private channel or group
   - Add the bot as admin
   - Configure in Mini App settings

2. **Use forum topics** (optional)
   - Create a forum-enabled group
   - Bot will create topics for different log types
   - Better organization for high-volume groups

3. **Test the configuration**
   - Use the "Test Logs" button in Mini App
   - Verify bot has permission to post

### For Developers

1. **Always log moderation actions**
   ```python
   await admin_service.log_custom_action(
       bot, group_id, admin_id, target_id,
       action="custom_action",
       reason="Description of what happened"
   )
   ```

2. **Include context in reasons**
   - Good: "Rule matched: No spam links"
   - Bad: "Rule matched"

3. **Handle log failures gracefully**
   - Log to database even if notification fails
   - Don't block the main action if logging fails

---

## Troubleshooting

### Logs not appearing in channel

**Check:**
1. Is `logs_enabled` true for the group?
2. Is `logs_chat_id` correctly set?
3. Is the bot an admin in the logs channel?
4. Does the bot have "Post Messages" permission?

**Solution:**
- Use "Test Logs" button in Mini App
- Check bot permissions in the channel
- Verify the chat ID is correct (use `/id` command)

### Forum topics not working

**Check:**
1. Is the logs destination a forum-enabled group?
2. Does the bot have "Manage Topics" permission?

**Solution:**
- Enable forum mode in group settings
- Grant bot "Manage Topics" permission
- Or use a regular channel/group instead

### Database logs but no notifications

**This is normal if:**
- Logs are disabled in group settings
- No logs channel is configured
- Bot can't access the logs channel

**All actions are always logged to database**, notifications are optional.

---

## Future Enhancements

### Potential Improvements
1. **Log filtering** - Filter by action type, admin, or date range
2. **Log export** - Export logs as CSV/JSON
3. **Log retention** - Auto-delete old logs after X days
4. **Log analytics** - Dashboard showing action statistics
5. **Webhook integration** - Send logs to external services

### Not Implemented
- Bot commands for logs configuration (use Mini App)
- Log search functionality
- Real-time log streaming
- Log aggregation across multiple groups

---

## Summary

The mod logs system is **fully functional** and provides:
- ✅ Complete action tracking in database
- ✅ Optional real-time notifications
- ✅ Easy configuration via Mini App
- ✅ Support for forum topics
- ✅ Graceful failure handling

All administrative actions are automatically logged. Notifications are optional and configured per-group.
