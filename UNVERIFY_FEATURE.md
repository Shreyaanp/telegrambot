# Unverify Feature - Implementation Complete ✅

## Overview

Added a new admin command `/vunverify` that allows administrators to **remove a user's verification status**, forcing them to verify again.

---

## What It Does

The `/vunverify` command:
1. **Deletes the user's verification record** from the database
2. **Mutes the user** in the group (since they're no longer verified)
3. **Updates group member status** to unverified
4. **Logs the action** in admin logs

---

## Use Cases

### 1. Second Chances
Give users who violated rules a chance to re-verify and rejoin properly.

### 2. Suspicious Activity
Reset verification for accounts showing suspicious behavior.

### 3. Testing
Test the verification flow without creating new accounts.

### 4. Account Compromised
If a verified account is compromised, unverify it to force re-verification.

### 5. Policy Changes
If verification requirements change, unverify all users to re-verify under new rules.

---

## Usage

### Basic Usage
```
/vunverify @username
/vunverify <user_id>
```

### Reply to Message
```
[Reply to user's message]
/vunverify
```

---

## Command Flow

```
Admin uses /vunverify @user
         ↓
Check if user is verified
         ↓
Delete verification record from database
         ↓
Update group member status
         ↓
Mute user in group
         ↓
Log action in admin logs
         ↓
Send confirmation message
```

---

## Example Output

```
✅ Verification Removed

User @john has been unverified and has been muted.

What this means:
• Their verification record has been deleted
• They must verify again to participate
• They can use /verify to start verification

Reason to use this:
• Give users a second chance
• Reset suspicious accounts
• Testing purposes
```

---

## Technical Implementation

### 1. New Method in UserService

**File:** `bot/services/user_service.py`

```python
async def delete_verification(self, telegram_id: int) -> bool:
    """
    Delete a user's verification record (unverify them).
    
    Returns:
        True if deleted successfully, False otherwise
    """
    async with self.db.session() as session:
        result = await session.execute(
            delete(User).where(User.telegram_id == telegram_id)
        )
        await session.commit()
        return result.rowcount > 0
```

### 2. New Command in AdminPlugin

**File:** `bot/plugins/admin.py`

```python
async def cmd_unverify(self, message: Message):
    """Remove a user's verification (unverify them)."""
    # Check admin permission
    # Extract target user
    # Delete verification
    # Mute user
    # Log action
    # Send confirmation
```

### 3. Updated Help Message

**File:** `bot/utils/messages.py`

Added `/vunverify @user - Remove user's verification` to help text.

---

## Files Modified

1. ✅ `bot/services/user_service.py` - Added `delete_verification()` method
2. ✅ `bot/plugins/admin.py` - Added `/vunverify` command handler
3. ✅ `bot/utils/messages.py` - Updated help message

---

## Admin Permissions Required

- ✅ `can_restrict_members` - Required to mute the unverified user

---

## Database Changes

**No schema changes required!** Uses existing tables:
- Deletes from `users` table
- Updates `group_members` table
- Logs to `admin_logs` table

---

## Testing Checklist

### Test 1: Unverify Verified User
1. Have a verified user in group
2. Admin uses `/vunverify @user`
3. ✅ User's verification deleted
4. ✅ User is muted
5. ✅ Confirmation message sent
6. ✅ Action logged

### Test 2: Unverify Unverified User
1. Have an unverified user
2. Admin uses `/vunverify @user`
3. ✅ Warning message: "User is not verified"

### Test 3: User Can Re-verify
1. Unverify a user
2. User types `/verify`
3. ✅ Verification process starts
4. ✅ User can complete verification
5. ✅ User is unmuted on success

### Test 4: Admin Logs
1. Unverify a user
2. Check `/adminlog`
3. ✅ Action is logged with details

---

## Error Handling

### User Not Found
```
⚠️ User <user_id> is not verified.

They don't have a verification record to remove.
```

### Database Error
```
❌ Failed to Remove Verification

Could not delete verification for user <user_id>.
This might be a database error. Please try again.
```

### Mute Failed
```
✅ Verification Removed

User @john has been unverified but could not be muted (check bot permissions).
```

---

## Admin Log Entry

When a user is unverified, the following is logged:

```json
{
  "action": "unverify",
  "admin_id": 123456789,
  "target_user_id": 987654321,
  "group_id": -1001234567890,
  "details": "Removed verification for John Doe",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## Comparison with /vverify

| Feature | /vverify | /vunverify |
|---------|----------|------------|
| Purpose | Manually verify user | Remove verification |
| Effect | Adds verification | Deletes verification |
| User Status | Unmuted | Muted |
| Database | Creates/updates record | Deletes record |
| Use Case | Bypass verification | Force re-verification |

---

## Future Enhancements (Optional)

### 1. Bulk Unverify
```
/vunverify_all - Unverify all users in group
```

### 2. Unverify with Reason
```
/vunverify @user <reason>
```

### 3. Temporary Unverify
```
/vunverify @user 24h - Unverify for 24 hours
```

### 4. Notification to User
Send DM to user when they're unverified with reason.

---

## Documentation Updates Needed

### 1. Website Commands Page
Add `/vunverify` to commands reference.

### 2. README.md
Add to admin commands list.

### 3. Help Command
✅ Already updated!

---

## Deployment

### No Database Migration Required
This feature uses existing tables, so no migration script is needed.

### Deployment Steps
1. Pull latest code from git
2. Restart bot service
3. Test `/vunverify` command
4. Update documentation (optional)

---

## Summary

✅ **Feature Complete!**

- New `/vunverify` command implemented
- Deletes user verification records
- Mutes unverified users
- Logs all actions
- Full error handling
- Ready for production

**Total Changes:**
- 3 files modified
- ~100 lines of code added
- 0 database migrations required
- Fully backward compatible

---

**🎉 The unverify feature is ready to use!**

