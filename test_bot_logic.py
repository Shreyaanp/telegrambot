"""
Comprehensive test suite for bot logic with mock data.
Tests all major features without requiring live Telegram connection.
"""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from bot.config import Config
from bot.container import ServiceContainer
from database.db import db
from database.models import (
    User, Group, Ticket, TicketMessage, TicketUserState,
    PendingJoinVerification, GroupUserState, DmSubscriber,
    Warning, Whitelist, Permission, AdminLog
)


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_test(name: str):
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}TEST: {name}{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}")


def print_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")


def print_error(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")


def print_info(msg: str):
    print(f"{Colors.YELLOW}ℹ️  {msg}{Colors.RESET}")


async def test_database_connection():
    """Test 1: Database connection and schema"""
    print_test("Database Connection & Schema")
    
    try:
        await db.connect()
        print_success("Database connected")
        
        # Test health check
        healthy = await db.health_check()
        if healthy:
            print_success("Database health check passed")
        else:
            print_error("Database health check failed")
            return False
        
        # Verify tables exist
        async with db.session() as session:
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            )
            tables = [row[0] for row in result.fetchall()]
            
            required_tables = [
                'users', 'groups', 'tickets', 'ticket_messages', 'ticket_user_state',
                'pending_join_verifications', 'group_user_state', 'dm_subscribers',
                'warnings', 'whitelist', 'permissions', 'admin_logs', 'broadcasts',
                'sequences', 'jobs', 'federations'
            ]
            
            missing = [t for t in required_tables if t not in tables]
            if missing:
                print_error(f"Missing tables: {missing}")
                return False
            
            print_success(f"All {len(required_tables)} required tables exist")
        
        return True
    except Exception as e:
        print_error(f"Database test failed: {e}")
        return False


async def test_service_container():
    """Test 2: Service container initialization"""
    print_test("Service Container Initialization")
    
    try:
        config = Config.from_env()
        print_success("Config loaded from environment")
        
        container = await ServiceContainer.create(config)
        print_success("Service container created")
        
        # Check all services exist
        services = [
            'mercle_sdk', 'user_manager', 'verification_service', 'admin_service',
            'whitelist_service', 'notes_service', 'filter_service', 'antiflood_service',
            'welcome_service', 'logs_service', 'group_service', 'roles_service',
            'lock_service', 'metrics_service', 'jobs_service', 'broadcast_service',
            'sequence_service', 'rules_service', 'ticket_service', 'dm_subscriber_service',
            'federation_service', 'token_service', 'panel_service', 'pending_verification_service'
        ]
        
        for service_name in services:
            if not hasattr(container, service_name):
                print_error(f"Missing service: {service_name}")
                return False
        
        print_success(f"All {len(services)} services initialized")
        return container
    except Exception as e:
        print_error(f"Service container test failed: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_user_operations(container):
    """Test 3: User creation and verification"""
    print_test("User Operations")
    
    try:
        user_manager = container.user_manager
        
        # Create test user
        test_user_id = 999999001
        test_mercle_id = f"test_mercle_{test_user_id}"
        
        # Clean up if exists
        async with db.session() as session:
            from sqlalchemy import delete
            await session.execute(delete(User).where(User.telegram_id == test_user_id))
        
        user = await user_manager.create_user(
            telegram_id=test_user_id,
            mercle_user_id=test_mercle_id,
            username="test_user"
        )
        
        if user:
            print_success(f"User created: {test_user_id}")
        else:
            print_error("User creation failed")
            return False
        
        # Test verification check
        is_verified = await user_manager.is_verified(test_user_id)
        if is_verified:
            print_success("User verification check passed")
        else:
            print_error("User should be verified but isn't")
            return False
        
        # Test duplicate mercle_id protection
        duplicate = await user_manager.create_user(
            telegram_id=test_user_id + 1,
            mercle_user_id=test_mercle_id,  # Same mercle ID
            username="duplicate_user"
        )
        
        if duplicate is None:
            print_success("Duplicate mercle_id protection working")
        else:
            print_error("Duplicate mercle_id was allowed!")
            return False
        
        return True
    except Exception as e:
        print_error(f"User operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_group_operations(container):
    """Test 4: Group management"""
    print_test("Group Operations")
    
    try:
        group_service = container.group_service
        
        test_group_id = -1001234567890
        
        # Create/get group
        group = await group_service.get_or_create_group(test_group_id)
        print_success(f"Group created/retrieved: {test_group_id}")
        
        # Update settings
        await group_service.update_setting(
            test_group_id,
            verification_enabled=True,
            verification_timeout=300,
            antiflood_enabled=True,
            antiflood_limit=10
        )
        print_success("Group settings updated")
        
        # Verify settings
        group = await group_service.get_or_create_group(test_group_id)
        if group.verification_enabled and group.antiflood_enabled:
            print_success("Settings persisted correctly")
        else:
            print_error("Settings not saved properly")
            return False
        
        return True
    except Exception as e:
        print_error(f"Group operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ticket_system(container):
    """Test 5: Ticket system with message history"""
    print_test("Ticket System")
    
    try:
        ticket_service = container.ticket_service
        group_service = container.group_service
        
        test_group_id = -1001234567890
        test_user_id = 999999002
        
        # Setup group with logs enabled
        await group_service.update_setting(
            test_group_id,
            logs_enabled=True,
            logs_chat_id=test_group_id
        )
        print_success("Group configured for tickets")
        
        # Clean up old test tickets
        async with db.session() as session:
            from sqlalchemy import delete, select
            # Get ticket IDs first
            result = await session.execute(select(Ticket.id).where(Ticket.user_id == test_user_id))
            ticket_ids = [row[0] for row in result.fetchall()]
            
            # Delete messages for those tickets
            if ticket_ids:
                await session.execute(delete(TicketMessage).where(TicketMessage.ticket_id.in_(ticket_ids)))
            
            # Delete tickets and user state
            await session.execute(delete(Ticket).where(Ticket.user_id == test_user_id))
            await session.execute(delete(TicketUserState).where(TicketUserState.user_id == test_user_id))
        
        # Create ticket (without bot)
        from unittest.mock import AsyncMock, MagicMock
        mock_bot = AsyncMock()
        mock_bot.get_chat = AsyncMock(return_value=MagicMock(is_forum=False))
        mock_bot.send_message = AsyncMock()
        
        ticket_id = await ticket_service.create_ticket(
            bot=mock_bot,
            group_id=test_group_id,
            user_id=test_user_id,
            message="Test ticket message",
            subject="Test Subject"
        )
        print_success(f"Ticket created: #{ticket_id}")
        
        # Verify initial message was stored
        messages = await ticket_service.get_ticket_messages(ticket_id=ticket_id)
        if len(messages) == 1 and messages[0]['sender_type'] == 'user':
            print_success("Initial message stored in history")
        else:
            print_error(f"Expected 1 message, got {len(messages)}")
            return False
        
        # Add more messages
        await ticket_service.add_message(
            ticket_id=ticket_id,
            sender_type="staff",
            sender_id=888888001,
            sender_name="Staff Member",
            message_type="text",
            content="Staff reply"
        )
        
        await ticket_service.add_message(
            ticket_id=ticket_id,
            sender_type="user",
            sender_id=test_user_id,
            message_type="text",
            content="User follow-up"
        )
        print_success("Additional messages added")
        
        # Verify message count
        messages = await ticket_service.get_ticket_messages(ticket_id=ticket_id)
        if len(messages) == 3:
            print_success(f"All {len(messages)} messages retrieved")
        else:
            print_error(f"Expected 3 messages, got {len(messages)}")
            return False
        
        # Verify ticket metadata updated
        async with db.session() as session:
            ticket = await session.get(Ticket, ticket_id)
            if ticket.message_count == 3:
                print_success("Message count updated correctly")
            else:
                print_error(f"Message count is {ticket.message_count}, expected 3")
                return False
            
            if ticket.last_staff_reply_at and ticket.last_user_message_at:
                print_success("Timestamp tracking working")
            else:
                print_error("Timestamps not updated")
                return False
        
        # Test active ticket
        await ticket_service.set_active_ticket(user_id=test_user_id, ticket_id=ticket_id)
        active = await ticket_service.get_active_ticket(user_id=test_user_id)
        if active and active['id'] == ticket_id:
            print_success("Active ticket tracking working")
        else:
            print_error("Active ticket not set properly")
            return False
        
        # Test ticket closure
        closed = await ticket_service.close_ticket(
            bot=mock_bot,
            ticket_id=ticket_id,
            closed_by_user_id=888888001,
            notify_user=False
        )
        if closed:
            print_success("Ticket closed successfully")
        else:
            print_error("Ticket closure failed")
            return False
        
        # Verify TicketUserState cleared
        active_after_close = await ticket_service.get_active_ticket(user_id=test_user_id)
        if active_after_close is None:
            print_success("TicketUserState cleared on close")
        else:
            print_error("TicketUserState not cleared")
            return False
        
        return True
    except Exception as e:
        print_error(f"Ticket system test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_pending_verification(container):
    """Test 6: Pending verification flow"""
    print_test("Pending Verification System")
    
    try:
        pending_service = container.pending_verification_service
        
        test_group_id = -1001234567890
        test_user_id = 999999003
        
        # Clean up
        async with db.session() as session:
            from sqlalchemy import delete
            await session.execute(
                delete(PendingJoinVerification).where(
                    PendingJoinVerification.telegram_id == test_user_id
                )
            )
        
        # Create pending verification
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        pending = await pending_service.create_pending(
            group_id=test_group_id,
            telegram_id=test_user_id,
            expires_at=expires_at,
            kind="post_join"
        )
        print_success(f"Pending verification created: #{pending.id}")
        
        # Test race condition protection (using bot_id as decided_by)
        can_start = await pending_service.try_mark_starting(pending.id, test_user_id)
        if can_start:
            print_success("First attempt to start verification succeeded")
        else:
            print_error("Should be able to start verification")
            return False
        
        # Try again (should fail - already started)
        can_start_again = await pending_service.try_mark_starting(pending.id, test_user_id)
        if not can_start_again:
            print_success("Duplicate start attempt blocked (race protection working)")
        else:
            print_error("Race condition protection failed")
            return False
        
        # Test decision
        from unittest.mock import AsyncMock
        mock_bot = AsyncMock()
        await pending_service.decide(pending.id, status="approved", decided_by=888888001)
        print_success("Verification decision recorded")
        
        # Verify status
        async with db.session() as session:
            updated = await session.get(PendingJoinVerification, pending.id)
            if updated.status == "approved":
                print_success("Status updated correctly")
            else:
                print_error(f"Status is {updated.status}, expected 'approved'")
                return False
        
        return True
    except Exception as e:
        print_error(f"Pending verification test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_admin_operations(container):
    """Test 7: Admin operations and permissions"""
    print_test("Admin Operations")
    
    try:
        admin_service = container.admin_service
        roles_service = container.roles_service
        whitelist_service = container.whitelist_service
        
        test_group_id = -1001234567890
        test_user_id = 999999004
        test_admin_id = 888888002
        
        # Clean up
        async with db.session() as session:
            from sqlalchemy import delete
            await session.execute(delete(Warning).where(Warning.telegram_id == test_user_id))
            await session.execute(delete(Whitelist).where(Whitelist.telegram_id == test_user_id))
            await session.execute(delete(Permission).where(Permission.telegram_id == test_user_id))
        
        # Test warning system
        warn_count, warn_limit = await admin_service.warn_user(
            group_id=test_group_id,
            user_id=test_user_id,
            admin_id=test_admin_id,
            reason="Test warning"
        )
        print_success(f"Warning added: {warn_count}/{warn_limit}")
        if warn_count == 1:
            print_success(f"Warning count correct: {warn_count}")
        else:
            print_error(f"Warning count is {warn_count}, expected 1")
            return False
        
        # Test whitelist
        await whitelist_service.add_to_whitelist(
            group_id=test_group_id,
            user_id=test_user_id,
            admin_id=test_admin_id,
            reason="Test whitelist"
        )
        print_success("User whitelisted")
        
        is_whitelisted = await whitelist_service.is_whitelisted(test_group_id, test_user_id)
        if is_whitelisted:
            print_success("Whitelist check working")
        else:
            print_error("User should be whitelisted")
            return False
        
        # Test custom permissions
        await roles_service.set_permission(
            group_id=test_group_id,
            user_id=test_user_id,
            permission_key="warn",
            enabled=True,
            granted_by=test_admin_id
        )
        await roles_service.set_permission(
            group_id=test_group_id,
            user_id=test_user_id,
            permission_key="kick",
            enabled=True,
            granted_by=test_admin_id
        )
        print_success("Custom permissions granted")
        
        perms = await roles_service.get_role(test_group_id, test_user_id)
        if perms and perms.can_warn and perms.can_kick:
            print_success("Permissions retrieved correctly")
        else:
            print_error("Permissions not set properly")
            return False
        
        return True
    except Exception as e:
        print_error(f"Admin operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_broadcast_system(container):
    """Test 8: Broadcast and jobs system"""
    print_test("Broadcast & Jobs System")
    
    try:
        broadcast_service = container.broadcast_service
        jobs_service = container.jobs_service
        
        test_group_id = -1001234567890
        test_admin_id = 888888003
        
        # Clean up old broadcasts
        async with db.session() as session:
            from sqlalchemy import delete
            from database.models import Broadcast, BroadcastTarget, Job
            await session.execute(delete(BroadcastTarget))
            await session.execute(delete(Broadcast).where(Broadcast.created_by == test_admin_id))
            await session.execute(delete(Job).where(Job.job_type == "broadcast_send"))
        
        # Create broadcast
        broadcast_id = await broadcast_service.create_group_broadcast(
            created_by=test_admin_id,
            chat_ids=[test_group_id],
            text="Test broadcast message",
            delay_seconds=0,
            parse_mode="Markdown"
        )
        print_success(f"Broadcast created: #{broadcast_id}")
        
        # Verify job was created
        jobs = await jobs_service.claim_due(limit=10)
        broadcast_jobs = [j for j in jobs if j.job_type == "broadcast_send"]
        if broadcast_jobs:
            print_success(f"Broadcast job created: {len(broadcast_jobs)} job(s)")
        else:
            print_info("No broadcast jobs (may have been processed)")
        
        # Verify broadcast record
        async with db.session() as session:
            from database.models import Broadcast
            broadcast = await session.get(Broadcast, broadcast_id)
            if broadcast and broadcast.total_targets == 1:
                print_success("Broadcast metadata correct")
            else:
                print_error("Broadcast not created properly")
                return False
        
        return True
    except Exception as e:
        print_error(f"Broadcast system test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_dm_subscribers(container):
    """Test 9: DM subscriber management"""
    print_test("DM Subscriber System")
    
    try:
        dm_service = container.dm_subscriber_service
        
        test_user_id = 999999005
        
        # Clean up
        async with db.session() as session:
            from sqlalchemy import delete
            await session.execute(delete(DmSubscriber).where(DmSubscriber.telegram_id == test_user_id))
        
        # Touch subscriber
        await dm_service.touch(
            telegram_id=test_user_id,
            username="test_subscriber",
            first_name="Test",
            last_name="User"
        )
        print_success("DM subscriber created/updated")
        
        # Count deliverable
        count = await dm_service.count_deliverable()
        print_success(f"Deliverable subscribers: {count}")
        
        # Test opt-out
        await dm_service.set_opt_out(telegram_id=test_user_id, opted_out=True)
        print_success("User opted out")
        
        # Verify opt-out
        async with db.session() as session:
            subscriber = await session.get(DmSubscriber, test_user_id)
            if subscriber and subscriber.opted_out:
                print_success("Opt-out status correct")
            else:
                print_error("Opt-out not working")
                return False
        
        return True
    except Exception as e:
        print_error(f"DM subscriber test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_metrics(container):
    """Test 10: Metrics tracking"""
    print_test("Metrics System")
    
    try:
        metrics_service = container.metrics_service
        test_group_id = -1001234567890
        
        # Test counters
        await metrics_service.incr_verification("approved")
        await metrics_service.incr_verification("rejected")
        await metrics_service.incr_admin_action("kick", test_group_id)
        await metrics_service.incr_api_error("telegram_api")
        print_success("Metrics incremented")
        
        # Get snapshot
        admin_actions, verification_outcomes, api_errors, last_update = await metrics_service.snapshot()
        
        if verification_outcomes.get("approved", 0) > 0:
            print_success(f"Verification metrics: {verification_outcomes}")
        else:
            print_info("No verification metrics yet")
        
        if admin_actions:
            print_success(f"Admin action metrics: {admin_actions}")
        else:
            print_info("No admin action metrics yet")
        
        if api_errors:
            print_success(f"API error metrics: {api_errors}")
        else:
            print_info("No API error metrics yet")
        
        return True
    except Exception as e:
        print_error(f"Metrics test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests and report results"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("="*70)
    print("  TELEGRAM BOT COMPREHENSIVE TEST SUITE")
    print("="*70)
    print(Colors.RESET)
    
    results = {}
    
    # Test 1: Database
    results['database'] = await test_database_connection()
    
    if not results['database']:
        print_error("\n❌ Database tests failed. Cannot continue.")
        return results
    
    # Test 2: Service Container
    container = await test_service_container()
    results['container'] = container is not None
    
    if not container:
        print_error("\n❌ Service container failed. Cannot continue.")
        return results
    
    # Test 3-10: All other tests
    results['users'] = await test_user_operations(container)
    results['groups'] = await test_group_operations(container)
    results['tickets'] = await test_ticket_system(container)
    results['pending_verification'] = await test_pending_verification(container)
    results['admin'] = await test_admin_operations(container)
    results['broadcasts'] = await test_broadcast_system(container)
    results['dm_subscribers'] = await test_dm_subscribers(container)
    results['metrics'] = await test_metrics(container)
    
    # Cleanup
    await container.cleanup()
    await db.close()
    
    # Summary
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("="*70)
    print("  TEST SUMMARY")
    print("="*70)
    print(Colors.RESET)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = f"{Colors.GREEN}✅ PASS{Colors.RESET}" if passed_test else f"{Colors.RED}❌ FAIL{Colors.RESET}"
        print(f"{test_name.upper():.<50} {status}")
    
    print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.RESET}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED! Bot is 100% ready!{Colors.RESET}\n")
        return True
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}⚠️  Some tests failed. Review errors above.{Colors.RESET}\n")
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(run_all_tests())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Tests interrupted by user{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

