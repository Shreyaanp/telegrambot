"""
MERCLE TELEGRAM BOT - DEVELOPMENT ROADMAP
==========================================
Generated: 2024-12-20
Last Updated: 2024-12-20
Status: IN PROGRESS - Phase 0, 1, 2 COMPLETE. Phase 3 PENDING.

This file serves as both documentation AND executable checklist.
Run `python ROADMAP.py` to see current progress.

PRIORITY LEVELS:
- P0: Blocking/Security - Must fix before any testing
- P1: Core functionality - Required for MVP
- P2: UX/Polish - Important for user experience  
- P3: Nice-to-have - Can defer post-launch
"""

ROADMAP = {
    # =========================================================================
    # PHASE 0: SECURITY FIXES (P0) - COMPLETE ✅
    # =========================================================================
    "phase_0_security": {
        "title": "🔒 Security Fixes",
        "priority": "P0",
        "estimated_hours": 4,
        "tasks": [
            {
                "id": "SEC-001",
                "title": "Webhook signature validation",
                "description": """
                    DONE: Added WEBHOOK_SECRET env var, validates X-Telegram-Bot-Api-Secret-Token header.
                    Files: webhook_server.py, bot/config.py
                """,
                "status": "completed",
            },
            {
                "id": "SEC-002", 
                "title": "Broadcast auth hardening",
                "description": """
                    DONE: Added BROADCAST_ADMIN_IDS env var, only listed users can DM broadcast.
                    Files: webhook_server.py, bot/config.py
                """,
                "status": "completed",
            },
            {
                "id": "SEC-003",
                "title": "ReDoS protection for rules regex",
                "description": """
                    DONE: Added regex validation, timeout protection, dangerous pattern detection.
                    Files: bot/services/rules_service.py
                """,
                "status": "completed",
            },
            {
                "id": "SEC-004",
                "title": "Hide webhook path from root endpoint",
                "description": """
                    DONE: Removed webhook path from / endpoint response.
                    Files: webhook_server.py
                """,
                "status": "completed",
            },
        ]
    },

    # =========================================================================
    # PHASE 1: CRITICAL BUG FIXES (P1) - COMPLETE ✅
    # =========================================================================
    "phase_1_bugs": {
        "title": "🐛 Critical Bug Fixes", 
        "priority": "P1",
        "estimated_hours": 6,
        "tasks": [
            {
                "id": "BUG-001",
                "title": "Fix navigation history stack",
                "description": """
                    DONE: Implemented proper history stack with view state capture/restore.
                    Files: static/app.html
                """,
                "status": "completed",
            },
            {
                "id": "BUG-002",
                "title": "Fix ticket loading errors",
                "description": """
                    DONE: Fixed API endpoints and frontend ticket detail loading.
                    Files: static/app.html, webhook_server.py
                """,
                "status": "completed",
            },
            {
                "id": "BUG-003",
                "title": "Fix rules edit/delete functionality",
                "description": """
                    DONE: Added confirmation dialog, better spacing, proper API calls.
                    Files: static/app.html, webhook_server.py
                """,
                "status": "completed",
            },
            {
                "id": "BUG-004",
                "title": "Fix broadcast transaction blocking",
                "description": """
                    DONE: Split into 2 transactions - fetch/claim targets, then send outside TX.
                    Files: bot/services/broadcast_service.py
                """,
                "status": "completed",
            },
            {
                "id": "BUG-005",
                "title": "Add unique constraint to group_members",
                "description": """
                    DONE: Added migration with duplicate cleanup and unique constraint.
                    Files: database/models.py, alembic migration
                """,
                "status": "completed",
            },
            {
                "id": "BUG-006",
                "title": "Remove dead code in rules_service",
                "description": """
                    DONE: Removed unreachable return None.
                    Files: bot/services/rules_service.py
                """,
                "status": "completed",
            },
        ]
    },

    # =========================================================================
    # PHASE 2: UI/UX CONSISTENCY (P1) - COMPLETE ✅
    # =========================================================================
    "phase_2_design_system": {
        "title": "🎨 Design System & UI Consistency",
        "priority": "P1", 
        "estimated_hours": 8,
        "tasks": [
            {
                "id": "UI-001",
                "title": "Create unified design system",
                "description": """
                    DONE: Added CSS variables, form validation styles, consistent spacing.
                    Files: static/app.html
                """,
                "status": "completed",
            },
            {
                "id": "UI-002",
                "title": "Fix touch interactions",
                "description": """
                    DONE: Removed hover-only effects, using :active states.
                    Files: static/app.html
                """,
                "status": "completed",
            },
            {
                "id": "UI-003",
                "title": "Improve header back button",
                "description": """
                    DONE: Added "Back" text label, better styling.
                    Files: static/app.html
                """,
                "status": "completed",
            },
            {
                "id": "UI-004",
                "title": "Fix status page overflow",
                "description": """
                    DONE: Changed to min-height with overflow-y: auto.
                    Files: static/app.html
                """,
                "status": "completed",
            },
            {
                "id": "UI-005",
                "title": "Add group search empty state",
                "description": """
                    DONE: Added "No groups found" message with clear search button.
                    Files: static/app.html
                """,
                "status": "completed",
            },
            {
                "id": "UI-006",
                "title": "Redesign analytics page",
                "description": """
                    DONE: Complete redesign with gradient cards, progress bars, icons.
                    Files: static/app.html
                """,
                "status": "completed",
            },
            {
                "id": "UI-007",
                "title": "Add form validation indicators",
                "description": """
                    DONE: Added .has-error, .form-error, .required-indicator CSS.
                    Files: static/app.html
                """,
                "status": "completed",
            },
            {
                "id": "UI-008",
                "title": "Fix settings save UX",
                "description": """
                    DONE: Added sticky save bar, saving state, success feedback.
                    Files: static/app.html
                """,
                "status": "completed",
            },
            {
                "id": "UI-009",
                "title": "Fix rules delete UX",
                "description": """
                    DONE: Added spacing, confirmation dialog using Telegram's showConfirm.
                    Files: static/app.html
                """,
                "status": "completed",
            },
        ]
    },

    # =========================================================================
    # PHASE 3: FEATURE COMPLETENESS (P1) - PENDING
    # =========================================================================
    "phase_3_features": {
        "title": "✨ Feature Completeness",
        "priority": "P1",
        "estimated_hours": 12,
        "tasks": [
            {
                "id": "FEAT-001",
                "title": "Verification flow return logic",
                "description": """
                    Problem: Verification flow jumps to bot DM without guidance or return.
                    
                    Solution:
                    1. Show clear instructions before redirect
                    2. After verification completes, send user back to Mini App or group
                    3. Add deep link that reopens Mini App after verification
                    
                    Files: static/app.html, bot/handlers/commands.py, bot/services/verification.py
                """,
                "status": "pending",
            },
            {
                "id": "FEAT-002",
                "title": "Welcome message channel choice",
                "description": """
                    Problem: No choice for welcome message destination (group vs DM).
                    
                    Solution:
                    1. Add setting: welcome_destination (group/dm/both)
                    2. Update onboarding service to respect this setting
                    3. Add to Mini App settings UI
                    
                    Files: database/models.py, bot/services/onboarding_service.py, 
                           static/app.html, webhook_server.py
                """,
                "status": "pending",
            },
            {
                "id": "FEAT-003",
                "title": "Rules: warn count before escalation",
                "description": """
                    Problem: If rule action is "warn", how many warnings before kick?
                    
                    Solution:
                    1. Add warn_threshold field to rules
                    2. Track warning count per user per rule
                    3. Escalate to kick/ban after threshold
                    
                    Files: database/models.py, bot/services/rules_service.py, static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "FEAT-004",
                "title": "Ticket system improvements",
                "description": """
                    Problems:
                    - UI/UX is bad for ticket creation
                    - No image support
                    - Bot doesn't ask enough questions
                    
                    Solution:
                    1. Multi-step ticket creation wizard in DM
                    2. Image handling (up to 5MB, save locally)
                    3. Priority levels (low/medium/high/urgent)
                    
                    Files: bot/handlers/commands.py, bot/services/ticket_service.py,
                           database/models.py, static/app.html, webhook_server.py
                """,
                "status": "pending",
            },
            {
                "id": "FEAT-005",
                "title": "Re-verification flow audit",
                "description": """
                    Problem: Need to check re-verification logic for gaps.
                    
                    Audit checklist:
                    1. What happens when verification expires?
                    2. Is user automatically restricted again?
                    3. How does re-verify button work?
                    4. Are there race conditions?
                    5. Does it work for users in multiple groups?
                    
                    Files: bot/services/verification.py, bot/handlers/member_events.py
                """,
                "status": "pending",
            },
            {
                "id": "FEAT-006",
                "title": "Improve bot response messages",
                "description": """
                    Problem: Bot output messages need to be better/more helpful.
                    
                    Solution:
                    1. Audit all bot responses
                    2. Make them more conversational and helpful
                    3. Add context-specific tips
                    4. Ensure consistent tone
                    
                    Files: All handler files
                """,
                "status": "pending",
            },
            {
                "id": "FEAT-007",
                "title": "Document mod logs flow",
                "description": """
                    Problem: Unclear how mod logs are created and work.
                    
                    Solution:
                    1. Audit current implementation
                    2. Document the flow
                    3. Ensure all mod actions are logged
                    4. Make logs destination configurable in Mini App
                    
                    Files: bot/services/mod_log_service.py, webhook_server.py
                """,
                "status": "pending",
            },
        ]
    },

    # =========================================================================
    # PHASE 4: PERFORMANCE (P2) - PENDING
    # =========================================================================
    "phase_4_performance": {
        "title": "⚡ Performance Optimization",
        "priority": "P2",
        "estimated_hours": 6,
        "tasks": [
            {
                "id": "PERF-001",
                "title": "Mini-app bootstrap optimization",
                "description": """
                    Problem: Bootstrap makes multiple Telegram API calls per group 
                    (admin check, preflight, member count) across up to 200 groups.
                    Can rate-limit or slow UI.
                    
                    Solution:
                    1. Lazy-load group details (only fetch when group selected)
                    2. Cache admin status (5-minute TTL)
                    3. Batch API calls where possible
                    4. Show loading states in UI
                    
                    Files: webhook_server.py:449
                """,
                "status": "pending",
            },
        ]
    },

    # =========================================================================
    # PHASE 5: ADVANCED FEATURES (P3) - PENDING
    # =========================================================================
    "phase_5_advanced": {
        "title": "🚀 Advanced Features",
        "priority": "P3",
        "estimated_hours": 20,
        "tasks": [
            {
                "id": "ADV-001",
                "title": "T5 content filtering model",
                "description": """
                    Goal: Use T5 model for intelligent content filtering by category.
                    
                    Implementation plan:
                    1. Local implementation first (can convert to API later)
                    2. Categories: spam, hate speech, adult content, scam, etc.
                    3. Model: distilbert or similar lightweight model
                    4. Integration points:
                       - Message handler checks content
                       - Returns category + confidence
                       - Rules engine uses this for actions
                    
                    Infrastructure notes:
                    - Will need GPU for reasonable performance
                    - User will move to better infra later
                    - Design as pluggable service
                    
                    Files: New bot/services/content_filter_service.py
                """,
                "status": "pending",
            },
            {
                "id": "ADV-002",
                "title": "User roles system",
                "description": """
                    Goal: Granular permission system for users.
                    
                    Current: Basic admin/mod detection from Telegram
                    
                    Proposed:
                    1. Custom roles (owner, admin, moderator, trusted, member)
                    2. Per-role permissions (can_warn, can_kick, can_ban, can_settings, etc.)
                    3. Role assignment via commands and Mini App
                    4. Role-based UI in Mini App
                    
                    Files: database/models.py, bot/services/roles_service.py,
                           webhook_server.py, static/app.html
                """,
                "status": "pending",
            },
        ]
    },
}

# =========================================================================
# EXECUTION ORDER
# =========================================================================
EXECUTION_ORDER = [
    "phase_0_security",   # COMPLETE ✅
    "phase_1_bugs",       # COMPLETE ✅
    "phase_2_design_system",  # COMPLETE ✅
    "phase_3_features",   # IN PROGRESS
    "phase_4_performance", # PENDING
    "phase_5_advanced",   # PENDING (post-MVP)
]

# =========================================================================
# HELPER FUNCTIONS
# =========================================================================
def print_roadmap():
    """Print current roadmap status."""
    total_tasks = 0
    completed_tasks = 0
    total_hours = 0
    
    print("\n" + "=" * 70)
    print("MERCLE TELEGRAM BOT - DEVELOPMENT ROADMAP")
    print("=" * 70 + "\n")
    
    for phase_key in EXECUTION_ORDER:
        phase = ROADMAP[phase_key]
        phase_tasks = phase["tasks"]
        phase_completed = sum(1 for t in phase_tasks if t["status"] == "completed")
        
        total_tasks += len(phase_tasks)
        completed_tasks += phase_completed
        total_hours += phase["estimated_hours"]
        
        status_icon = "✅" if phase_completed == len(phase_tasks) else "🔄" if phase_completed > 0 else "⏳"
        
        print(f"{status_icon} {phase['title']} ({phase['priority']})")
        print(f"   Progress: {phase_completed}/{len(phase_tasks)} tasks | Est: {phase['estimated_hours']}h")
        print()
        
        for task in phase_tasks:
            task_icon = "✅" if task["status"] == "completed" else "🔄" if task["status"] == "in_progress" else "⬜"
            print(f"   {task_icon} [{task['id']}] {task['title']}")
        
        print()
    
    print("=" * 70)
    print(f"TOTAL: {completed_tasks}/{total_tasks} tasks completed | Est: {total_hours}h total")
    print("=" * 70 + "\n")

def get_next_tasks(count=5):
    """Get next tasks to work on."""
    tasks = []
    for phase_key in EXECUTION_ORDER:
        phase = ROADMAP[phase_key]
        for task in phase["tasks"]:
            if task["status"] == "pending":
                tasks.append({
                    "phase": phase["title"],
                    "priority": phase["priority"],
                    **task
                })
                if len(tasks) >= count:
                    return tasks
    return tasks

if __name__ == "__main__":
    print_roadmap()
    
    print("\n📋 NEXT TASKS TO WORK ON:")
    print("-" * 40)
    for task in get_next_tasks(5):
        print(f"[{task['priority']}] {task['id']}: {task['title']}")
    print()
