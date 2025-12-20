"""
MERCLE TELEGRAM BOT - DEVELOPMENT ROADMAP
==========================================
Generated: 2024-12-20
Status: PLANNING PHASE

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
    # PHASE 0: SECURITY FIXES (P0) - Do these FIRST
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
                    Problem: Webhook accepts unsigned requests. Anyone who finds the 
                    webhook URL can POST forged updates.
                    
                    Solution: 
                    1. Add Telegram's secret_token parameter when setting webhook
                    2. Validate X-Telegram-Bot-Api-Secret-Token header on every request
                    3. Return 401 for invalid/missing tokens
                    
                    Files: webhook_server.py, bot/main.py
                """,
                "status": "pending",
            },
            {
                "id": "SEC-002", 
                "title": "Broadcast auth hardening",
                "description": """
                    Problem: Any user with 'settings' access in ANY group can broadcast 
                    to the ENTIRE subscriber list. A compromised admin = mass spam.
                    
                    Solution:
                    1. Create BROADCAST_ADMIN_IDS env var (comma-separated Telegram IDs)
                    2. Only users in this list can trigger broadcasts
                    3. Add audit logging for all broadcast attempts
                    
                    Files: webhook_server.py:874, webhook_server.py:900
                """,
                "status": "pending",
            },
            {
                "id": "SEC-003",
                "title": "ReDoS protection for rules regex",
                "description": """
                    Problem: User-defined regex patterns execute on every message with 
                    no timeout. Malicious patterns can spike CPU.
                    
                    Solution:
                    1. Add regex complexity validator (max length, no nested quantifiers)
                    2. Execute regex with timeout (use regex module with timeout or subprocess)
                    3. Cache compiled patterns
                    
                    Files: bot/services/rules_service.py:200
                """,
                "status": "pending",
            },
            {
                "id": "SEC-004",
                "title": "Hide webhook path from root endpoint",
                "description": """
                    Problem: Root endpoint exposes webhook path in response.
                    
                    Solution: Remove webhook path from any public responses.
                    
                    Files: webhook_server.py
                """,
                "status": "pending",
            },
        ]
    },

    # =========================================================================
    # PHASE 1: CRITICAL BUG FIXES (P1)
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
                    Problem: Back button doesn't maintain proper history. Going to 
                    ticket A, then ticket B, pressing back goes to ticket A not list.
                    
                    Solution:
                    1. Implement proper history stack (array of {view, state} objects)
                    2. Push to stack on forward navigation
                    3. Pop from stack on back navigation
                    4. Clear stack appropriately on major navigation changes
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "BUG-002",
                "title": "Fix ticket loading errors",
                "description": """
                    Problem: Tickets fail to load in Mini App.
                    
                    Solution: Debug API calls, check error handling, ensure proper
                    state management.
                    
                    Files: static/app.html, webhook_server.py
                """,
                "status": "pending",
            },
            {
                "id": "BUG-003",
                "title": "Fix rules edit/delete functionality",
                "description": """
                    Problem: Rules cannot be edited or deleted from Mini App.
                    
                    Solution:
                    1. Add edit endpoint and UI
                    2. Fix delete endpoint
                    3. Add confirmation dialog for delete
                    
                    Files: static/app.html, webhook_server.py, bot/services/rules_service.py
                """,
                "status": "pending",
            },
            {
                "id": "BUG-004",
                "title": "Fix broadcast transaction blocking",
                "description": """
                    Problem: Broadcast holds DB transaction while calling Telegram APIs,
                    blocking other writers and potentially exhausting connection pool.
                    
                    Solution:
                    1. Fetch and lock targets in one transaction
                    2. Commit immediately
                    3. Send messages in separate batches without holding transaction
                    
                    Files: bot/services/broadcast_service.py:238, :265
                """,
                "status": "pending",
            },
            {
                "id": "BUG-005",
                "title": "Add unique constraint to group_members",
                "description": """
                    Problem: No unique constraint on (group_id, telegram_id) allows
                    duplicate entries that skew state.
                    
                    Solution:
                    1. Create migration to add unique constraint
                    2. Handle duplicates during insertion with ON CONFLICT
                    
                    Files: database/models.py:170, new migration
                """,
                "status": "pending",
            },
            {
                "id": "BUG-006",
                "title": "Remove dead code in rules_service",
                "description": """
                    Problem: Unreachable return None at end of apply_group_text_rules.
                    
                    Solution: Remove dead code.
                    
                    Files: bot/services/rules_service.py:447
                """,
                "status": "pending",
            },
        ]
    },

    # =========================================================================
    # PHASE 2: UI/UX CONSISTENCY (P1)
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
                    Problem: Visual density inconsistent - some screens airy, others tight.
                    Feels like multiple products stitched together.
                    
                    Solution:
                    1. Define spacing scale (4px base: 4, 8, 12, 16, 24, 32, 48)
                    2. Define typography scale (consistent font sizes, weights)
                    3. Define component patterns (cards, buttons, inputs, lists)
                    4. Apply consistently across all views
                    
                    Files: static/app.html (CSS section)
                """,
                "status": "pending",
            },
            {
                "id": "UI-002",
                "title": "Fix touch interactions",
                "description": """
                    Problem: Hover animations imply desktop interactivity that doesn't 
                    exist on touch devices.
                    
                    Solution:
                    1. Remove hover-only effects or make them touch-friendly
                    2. Use :active states for touch feedback
                    3. Ensure tap targets are at least 44px
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "UI-003",
                "title": "Improve header back button",
                "description": """
                    Problem: Back button is only an icon with accent color, low affordance.
                    
                    Solution:
                    1. Add text label "Back" next to icon
                    2. Use distinct styling from accent color
                    3. Ensure consistent placement
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "UI-004",
                "title": "Fix status page overflow",
                "description": """
                    Problem: Status page locks to single screen height but can overflow
                    on smaller devices or with longer names/translated text.
                    
                    Solution:
                    1. Use min-height instead of fixed height
                    2. Allow scrolling when content overflows
                    3. Test with long text strings
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "UI-005",
                "title": "Add group search empty state",
                "description": """
                    Problem: Group search never shows "no results" state.
                    
                    Solution:
                    1. Track visible count after filtering
                    2. Show "No groups found" message
                    3. Add "Clear search" action
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "UI-006",
                "title": "Redesign analytics page",
                "description": """
                    Problem: Analytics page "looks like a 5 year old made it".
                    
                    Solution:
                    1. Use proper data visualization (charts or well-designed stats cards)
                    2. Group related metrics
                    3. Add time period selector
                    4. Make it actually useful
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "UI-007",
                "title": "Add form validation indicators",
                "description": """
                    Problem: Form inputs don't show validation until popup error.
                    
                    Solution:
                    1. Add "required" indicators to required fields
                    2. Show inline validation errors
                    3. Highlight invalid fields
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "UI-008",
                "title": "Fix settings save UX",
                "description": """
                    Problem: Settings changes look immediate but require "Save All Settings".
                    
                    Solution (pick one):
                    A) Auto-save with debounce + success indicator
                    B) Sticky save bar + dirty-state indicator
                    
                    Recommendation: Auto-save for toggles, explicit save for text fields.
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
            {
                "id": "UI-009",
                "title": "Fix rules delete UX",
                "description": """
                    Problem: Delete icon sits next to toggle, easy to accidentally tap.
                    
                    Solution:
                    1. Add more spacing between toggle and delete
                    2. Add confirmation dialog for delete
                    
                    Files: static/app.html
                """,
                "status": "pending",
            },
        ]
    },

    # =========================================================================
    # PHASE 3: FEATURE COMPLETENESS (P1)
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
                    1. Multi-step ticket creation wizard in DM:
                       - Ask for category/priority first
                       - Ask for detailed description
                       - Ask if they want to attach images
                    2. Image handling:
                       - Accept images up to 5MB
                       - Save to local storage (static/tickets/)
                       - Store file path in ticket_messages
                       - Display in Mini App ticket view
                    3. Priority levels:
                       - Add priority field (low/medium/high/urgent)
                       - Color-code in UI
                       - Sort by priority
                    
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
    # PHASE 4: PERFORMANCE (P2)
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
    # PHASE 5: ADVANCED FEATURES (P3)
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
    "phase_0_security",   # MUST be first - security issues
    "phase_1_bugs",       # Critical bugs blocking functionality
    "phase_2_design_system",  # UI consistency
    "phase_3_features",   # Feature completeness
    "phase_4_performance", # Performance (can do in parallel with phase 3)
    "phase_5_advanced",   # Advanced features (post-MVP)
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

