"""Service container - wires configuration, SDK clients, and domain services."""
import logging
from dataclasses import dataclass

from bot.config import Config
from bot.services.mercle_sdk import MercleSDK
from bot.services.user_manager import UserManager
from bot.services.verification import VerificationService
from bot.services.admin_service import AdminService
from bot.services.whitelist_service import WhitelistService
from bot.services.notes_service import NotesService
from bot.services.filter_service import FilterService
from bot.services.antiflood_service import AntiFloodService
from bot.services.welcome_service import WelcomeService
from bot.services.logs_service import LogsService
from bot.services.group_service import GroupService
from bot.services.roles_service import RolesService
from bot.services.lock_service import LockService
from bot.services.metrics_service import MetricsService
from bot.services.jobs_service import JobsService
from bot.services.broadcast_service import BroadcastService
from bot.services.sequence_service import SequenceService
from bot.services.rules_service import RulesService
from bot.services.ticket_service import TicketService
from bot.services.dm_subscriber_service import DmSubscriberService
from bot.services.federation_service import FederationService
from bot.services.token_service import TokenService
from bot.services.panel_service import PanelService
from bot.services.pending_verification_service import PendingVerificationService

logger = logging.getLogger(__name__)


@dataclass
class ServiceContainer:
    """Simple dependency container to share services across handlers."""
    
    config: Config
    mercle_sdk: MercleSDK
    user_manager: UserManager
    verification_service: VerificationService
    admin_service: AdminService
    whitelist_service: WhitelistService
    notes_service: NotesService
    filter_service: FilterService
    antiflood_service: AntiFloodService
    welcome_service: WelcomeService
    logs_service: LogsService
    group_service: GroupService
    roles_service: RolesService
    lock_service: LockService
    metrics_service: MetricsService
    jobs_service: JobsService
    broadcast_service: BroadcastService
    sequence_service: SequenceService
    rules_service: RulesService
    ticket_service: TicketService
    dm_subscriber_service: DmSubscriberService
    federation_service: FederationService
    token_service: TokenService
    panel_service: PanelService
    pending_verification_service: PendingVerificationService
    
    @classmethod
    async def create(cls, config: Config) -> "ServiceContainer":
        """
        Build the service container with all dependencies.
        
        Args:
            config: Loaded Config instance
        
        Returns:
            ServiceContainer with initialized services
        """
        logger.info("Building service container...")
        
        mercle_sdk = MercleSDK(config.mercle_api_url, config.mercle_api_key)
        user_manager = UserManager()
        group_service = GroupService()

        metrics_service = MetricsService()
        jobs_service = JobsService()
        broadcast_service = BroadcastService(jobs=jobs_service)
        sequence_service = SequenceService(jobs=jobs_service)
        rules_service = RulesService()
        ticket_service = TicketService()
        dm_subscriber_service = DmSubscriberService()
        federation_service = FederationService()
        pending_verification_service = PendingVerificationService()
        verification_service = VerificationService(
            config,
            mercle_sdk,
            user_manager,
            group_service,
            metrics_service,
            pending_verification_service=pending_verification_service,
            sequence_service=sequence_service,
        )
        admin_service = AdminService()
        whitelist_service = WhitelistService()
        notes_service = NotesService()
        filter_service = FilterService()
        antiflood_service = AntiFloodService()
        welcome_service = WelcomeService()
        logs_service = LogsService()
        roles_service = RolesService()
        lock_service = LockService()
        token_service = TokenService()
        panel_service = PanelService()
        
        logger.info("Service container ready")
        
        return cls(
            config=config,
            mercle_sdk=mercle_sdk,
            user_manager=user_manager,
            verification_service=verification_service,
            admin_service=admin_service,
            whitelist_service=whitelist_service,
            notes_service=notes_service,
            filter_service=filter_service,
            antiflood_service=antiflood_service,
            welcome_service=welcome_service,
            logs_service=logs_service,
            group_service=group_service,
            roles_service=roles_service,
            lock_service=lock_service,
            metrics_service=metrics_service,
            jobs_service=jobs_service,
            broadcast_service=broadcast_service,
            sequence_service=sequence_service,
            rules_service=rules_service,
            ticket_service=ticket_service,
            dm_subscriber_service=dm_subscriber_service,
            federation_service=federation_service,
            token_service=token_service,
            panel_service=panel_service,
            pending_verification_service=pending_verification_service,
        )
    
    async def cleanup(self):
        """Cleanup hook for future resources (kept for symmetry)."""
        try:
            await self.verification_service.shutdown()
        except Exception:
            pass
        try:
            await self.mercle_sdk.close()
        except Exception:
            pass
        logger.info("Service container cleanup complete")
