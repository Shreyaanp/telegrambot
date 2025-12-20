"""
MERCLE TELEGRAM BOT - DEVELOPMENT ROADMAP
==========================================
Generated: 2024-12-20
Last Updated: 2024-12-20
Status: IN PROGRESS - Phase 0, 1, 2 COMPLETE. Phase 3 (UX) IN PROGRESS.

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
    # PHASE 3: UX IMPROVEMENTS (P1) - IN PROGRESS
    # =========================================================================
    "phase_3_ux": {
        "title": "🎯 UX Improvements",
        "priority": "P1",
        "estimated_hours": 8,
        "tasks": [
            {
                "id": "UX-001",
                "title": "Remove duplicate Welcome Messages from Settings",
                "description": """
                    Problem: Welcome Messages section exists in both Settings page AND 
                    Onboarding page - confusing duplicate.
                    
                    Solution: Remove Welcome Messages from Settings, keep only Onboarding page.
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "UX-002",
                "title": "Mod logs - simple message in group, details in Mini App",
                "description": """
                    Problem: Detailed log messages with IDs shown in group chat.
                    
                    Solution:
                    1. Keep simple message in group (e.g., "User was muted for 1 minute")
                    2. Detailed logs viewable only in Mini App Settings → Logs section
                    3. Scrollable list of recent logs (timestamp, action, target, admin, reason)
                    
                    Files: static/app.html, webhook_server.py, bot/services/mod_log_service.py
                """,
                "status": "pending",
            },
            {
                "id": "UX-003",
                "title": "Smart verification button (mobile-aware)",
                "description": """
                    Problem: QR code shows on mobile, should only show on desktop.
                    Download button isn't smart about app detection.
                    
                    Solution:
                    1. Mobile: Smart button that tries mercle:// deep link, falls back to store
                    2. Desktop: Show QR code as-is
                    3. Use Android Intent fallback logic from verify.html
                    
                    Files: bot/services/verification.py, bot/handlers/commands.py
                """,
                "status": "pending",
            },
            {
                "id": "UX-004",
                "title": "Remove /menu command entirely",
                "description": """
                    Problem: Users shouldn't configure menu via commands.
                    
                    Solution: Remove /menu command and all related code.
                    
                    Files: bot/handlers/commands.py, bot/main.py
                """,
                "status": "pending",
            },
            {
                "id": "UX-005",
                "title": "Remove 'Add to group' from /start for unverified users",
                "description": """
                    Problem: Unverified users see "Add to group" option which doesn't make sense.
                    
                    Solution: Remove that option from /start response for unverified users.
                    
                    Files: bot/handlers/commands.py
                """,
                "status": "pending",
            },
            {
                "id": "UX-006",
                "title": "Mini App Verify button links directly to verification",
                "description": """
                    Problem: Clicking Verify in Mini App shows popup but doesn't link to 
                    actual verification flow.
                    
                    Solution: Link directly to verification (same as /start for unverified).
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "UX-007",
                "title": "Remove 'Return to Mini App' when user verified manually",
                "description": """
                    Problem: Shows "Return to Mini App" even when user verified via bot 
                    directly (not from Mini App).
                    
                    Solution: Only show return button if user came from Mini App.
                    
                    Files: bot/services/verification.py
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
}

# =========================================================================
# EXECUTION ORDER
# =========================================================================
EXECUTION_ORDER = [
    "phase_0_security",      # COMPLETE ✅
    "phase_1_bugs",          # COMPLETE ✅
    "phase_2_design_system", # COMPLETE ✅
    "phase_3_ux",            # IN PROGRESS
    "phase_4_performance",   # PENDING
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
    for task in get_next_tasks(7):
        print(f"[{task['priority']}] {task['id']}: {task['title']}")
    print()
