# Re-Verification Flow Audit Report
**Date:** 2024-12-20  
**Status:** ✅ AUDIT COMPLETE

## Executive Summary
The re-verification system is **mostly working correctly** with a few minor gaps. The system properly tracks verification expiration (7 days) and shows warnings in the Mini App, but does NOT automatically restrict users when verification expires.

---

## Audit Findings

### 1. ✅ What happens when verification expires?

**Current Behavior:**
- Users have a `verified_until` timestamp set to 7 days from verification
- The `is_verified()` method correctly checks if `verified_until > datetime.utcnow()`
- Expired users return `False` from `is_verified()` check

**Location:** `bot/services/user_manager.py:18-30`

**Status:** ✅ WORKING CORRECTLY

---

### 2. ⚠️ Is user automatically restricted again?

**Current Behavior:**
- **NO automatic re-restriction** when verification expires
- Users who were previously verified can continue chatting after expiration
- Only NEW joins are checked for verification status
- Expired users are only blocked if they:
  - Try to join a NEW group during raid mode
  - Try to join without @username when `block_no_username` is enabled

**Locations:**
- `bot/handlers/member_events.py:196, 230` - Only checks on NEW joins
- `bot/handlers/message_handlers.py` - No verification check in message handler

**Issue:** Users can continue chatting indefinitely after verification expires if they don't leave/rejoin

**Recommendation:** Add a background job or message handler check to restrict expired users

**Status:** ⚠️ GAP IDENTIFIED

---

### 3. ✅ How does re-verify button work?

**Current Behavior:**
- Mini App shows re-verify warnings when verification is close to expiring
- "Re-verify" button calls `startVerification()` which opens bot DM with `/verify`
- Same flow as initial verification
- New verification extends `verified_until` by another 7 days

**Locations:**
- `static/app.html:1005, 1032, 1229, 1599, 1649` - UI warnings and buttons
- `static/app.html:1279` - `startVerification()` function
- `bot/services/user_manager.py:101, 113, 149, 163` - Updates `verified_until`

**Status:** ✅ WORKING CORRECTLY

---

### 4. ✅ Are there race conditions?

**Checked Scenarios:**
1. **Concurrent verification attempts:** Uses database unique constraint on `mercle_user_id`
2. **Multiple pending verifications:** Uses unique index `uq_pv_active` on `(group_id, telegram_id, kind, status='pending')`
3. **Token usage:** Tokens have `used_at` timestamp to prevent reuse

**Locations:**
- `database/models.py:26` - Unique constraint on `users.mercle_user_id`
- `database/models.py:462-470` - Unique index on pending verifications
- `database/models.py:483-492` - Token expiry and usage tracking

**Status:** ✅ PROTECTED AGAINST RACE CONDITIONS

---

### 5. ✅ Does it work for users in multiple groups?

**Current Behavior:**
- Verification is **GLOBAL** - one verification works for all groups
- `User` table is not group-specific
- `verified_until` applies across all groups
- Each group can have its own pending verification, but global verification bypasses it

**Locations:**
- `database/models.py:18-35` - Global `User` table
- `bot/handlers/member_events.py:196, 230` - Checks global `is_verified()`
- `bot/handlers/join_requests.py:128, 186` - Same global check

**Status:** ✅ WORKING AS DESIGNED (Global verification)

---

## Issues Summary

### Critical Issues: 0
None

### Medium Issues: 1
1. **No automatic re-restriction on expiration** - Users can chat indefinitely after verification expires if they don't rejoin

### Minor Issues: 0
None

---

## Recommendations

### 1. Add Expiration Enforcement (Optional)
**Priority:** Medium  
**Effort:** Low

Add a check in the message handler to restrict users with expired verification:

```python
# In bot/handlers/message_handlers.py
# After line 75 (user_id = message.from_user.id)

# Check if verification has expired
try:
    user = await container.user_manager.get_user(user_id)
    if user and user.verified_until:
        if user.verified_until < datetime.utcnow():
            # Verification expired - restrict user
            try:
                await message.bot.restrict_chat_member(
                    chat_id=group_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False)
                )
                # Notify user to re-verify
                await message.reply(
                    "⚠️ Your verification has expired. Please re-verify to continue chatting.\n"
                    "Open the Mini App and click 'Re-verify Now'."
                )
                return  # Stop processing this message
            except Exception as e:
                logger.error(f"Failed to restrict expired user: {e}")
except Exception:
    pass
```

### 2. Add Grace Period (Optional)
**Priority:** Low  
**Effort:** Low

Add a 24-hour grace period before restricting:
- Show warnings 3 days before expiration
- Show urgent warnings 1 day before
- Restrict only after grace period

---

## Conclusion

The re-verification system is **well-designed and functional**. The main gap is that expired users aren't automatically restricted, which may be intentional to avoid disrupting active users. The system correctly:
- Tracks expiration dates
- Shows warnings in the Mini App
- Allows easy re-verification
- Prevents race conditions
- Works globally across all groups

**Recommendation:** Implement automatic expiration enforcement if stricter security is needed, otherwise the current system is acceptable for most use cases.
