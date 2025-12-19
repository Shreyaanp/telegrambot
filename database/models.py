"""Database models - Complete schema for full-featured bot."""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index, BigInteger, text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Verified users table - global verification across all groups."""
    __tablename__ = "users"
    
    telegram_id = Column(BigInteger, primary_key=True, autoincrement=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    mercle_user_id = Column(String, nullable=False, unique=True)
    verified_at = Column(DateTime, default=datetime.utcnow)
    verified_until = Column(DateTime, nullable=True)  # Verification expires after 7 days
    is_banned = Column(Boolean, default=False)  # Global ban
    
    # Relationships
    memberships = relationship("GroupMember", back_populates="user")
    
    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"


class DmSubscriber(Base):
    """Users who can receive bot DMs (for marketing/support broadcasts)."""

    __tablename__ = "dm_subscribers"

    telegram_id = Column(BigInteger, primary_key=True, autoincrement=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)

    opted_out = Column(Boolean, nullable=False, default=False)
    deliverable = Column(Boolean, nullable=False, default=True)

    fail_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_ok_at = Column(DateTime, nullable=True)
    last_fail_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_dm_subscribers_delivery", "deliverable", "opted_out"),
        Index("idx_dm_subscribers_last_seen", "last_seen_at"),
    )

    def __repr__(self):
        return f"<DmSubscriber(telegram_id={self.telegram_id}, deliverable={self.deliverable}, opted_out={self.opted_out})>"


class Federation(Base):
    """Federations link multiple groups for shared moderation (ban once, apply everywhere)."""

    __tablename__ = "federations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    owner_id = Column(BigInteger, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    groups = relationship("Group", back_populates="federation")


class FederationBan(Base):
    """Federation ban list (fban)."""

    __tablename__ = "federation_bans"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    federation_id = Column(BigInteger, ForeignKey("federations.id"), nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    reason = Column(Text, nullable=True)
    banned_by = Column(BigInteger, nullable=False)
    banned_at = Column(DateTime, default=datetime.utcnow)

    federation = relationship("Federation")

    __table_args__ = (
        Index("idx_fed_bans_fed", "federation_id"),
        Index("idx_fed_bans_user", "telegram_id"),
        Index("uq_fed_ban", "federation_id", "telegram_id", unique=True),
    )


class Group(Base):
    """Group settings table - per-group configuration."""
    __tablename__ = "groups"
    
    group_id = Column(BigInteger, primary_key=True, autoincrement=False)
    group_name = Column(String, nullable=True)
    federation_id = Column(BigInteger, ForeignKey("federations.id"), nullable=True)
    
    # Verification settings
    verification_enabled = Column(Boolean, default=True)
    verification_timeout = Column(Integer, default=300)  # 5 minutes
    kick_unverified = Column(Boolean, default=True)
    join_gate_enabled = Column(Boolean, default=True)  # MANDATORY: If group uses join requests, only approve after verification
    require_rules_acceptance = Column(Boolean, default=False, nullable=False)
    captcha_enabled = Column(Boolean, default=False, nullable=False)
    captcha_style = Column(String, default="button", nullable=False)
    captcha_max_attempts = Column(Integer, default=3, nullable=False)
    block_no_username = Column(Boolean, default=False, nullable=False)
    
    # Welcome/Goodbye
    welcome_enabled = Column(Boolean, default=True)
    welcome_message = Column(Text, nullable=True)
    goodbye_enabled = Column(Boolean, default=False)
    goodbye_message = Column(Text, nullable=True)
    
    # Moderation settings
    warn_limit = Column(Integer, default=3)  # Kick after X warns
    antiflood_enabled = Column(Boolean, default=True)
    antiflood_limit = Column(Integer, default=10)  # Messages per minute
    antiflood_mute_seconds = Column(Integer, default=300)  # Mute duration when flooding
    silent_automations = Column(Boolean, default=False)
    raid_mode_until = Column(DateTime, nullable=True)
    lock_links = Column(Boolean, default=False)
    lock_media = Column(Boolean, default=False)

    # Logs destination
    logs_enabled = Column(Boolean, default=False)
    logs_chat_id = Column(BigInteger, nullable=True)
    logs_thread_id = Column(BigInteger, nullable=True)
    
    # Rules
    rules_text = Column(Text, nullable=True)
    
    # Metadata
    added_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    members = relationship("GroupMember", back_populates="group")
    sessions = relationship("VerificationSession", back_populates="group")
    warnings = relationship("Warning", back_populates="group")
    whitelist_entries = relationship("Whitelist", back_populates="group")
    permissions = relationship("Permission", back_populates="group")
    flood_records = relationship("FloodTracker", back_populates="group")
    notes = relationship("Note", back_populates="group")
    filters = relationship("Filter", back_populates="group")
    admin_logs = relationship("AdminLog", back_populates="group")
    sequences = relationship("Sequence", back_populates="group")
    federation = relationship("Federation", back_populates="groups")
    
    def __repr__(self):
        return f"<Group(group_id={self.group_id}, group_name={self.group_name})>"


class GroupMember(Base):
    """Group membership tracking table."""
    __tablename__ = "group_members"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    is_muted = Column(Boolean, default=False)
    
    # Relationships
    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="memberships")
    
    __table_args__ = (
        Index('idx_group_member', 'group_id', 'telegram_id'),
    )
    
    def __repr__(self):
        return f"<GroupMember(group_id={self.group_id}, telegram_id={self.telegram_id})>"


class VerificationSession(Base):
    """Active verification sessions table."""
    __tablename__ = "verification_sessions"
    
    session_id = Column(String, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False)
    telegram_username = Column(String, nullable=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=True)
    chat_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String, default="pending")  # pending, approved, rejected, expired
    message_ids = Column(Text, nullable=True)  # Comma-separated message IDs to delete
    
    # Relationships
    group = relationship("Group", back_populates="sessions")
    
    __table_args__ = (
        Index('idx_telegram_status', 'telegram_id', 'status'),
    )
    
    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at
    
    def __repr__(self):
        return f"<VerificationSession(session_id={self.session_id}, status={self.status})>"


class Warning(Base):
    """Warning system table."""
    __tablename__ = "warnings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    warned_by = Column(BigInteger, nullable=False)  # Admin telegram_id
    reason = Column(Text, nullable=True)
    warned_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="warnings")
    
    __table_args__ = (
        Index('idx_group_user_warnings', 'group_id', 'telegram_id'),
    )
    
    def __repr__(self):
        return f"<Warning(group_id={self.group_id}, telegram_id={self.telegram_id})>"


class Whitelist(Base):
    """Whitelist table - users who bypass verification."""
    __tablename__ = "whitelist"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    added_by = Column(BigInteger, nullable=False)  # Admin telegram_id
    reason = Column(Text, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="whitelist_entries")
    
    __table_args__ = (
        Index('idx_group_user_whitelist', 'group_id', 'telegram_id'),
    )
    
    def __repr__(self):
        return f"<Whitelist(group_id={self.group_id}, telegram_id={self.telegram_id})>"


class Permission(Base):
    """Custom permissions table - for non-Telegram admins."""
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    role = Column(String, default="moderator")  # moderator, helper
    can_verify = Column(Boolean, default=False)
    can_kick = Column(Boolean, default=False)
    can_ban = Column(Boolean, default=False)
    can_warn = Column(Boolean, default=False)
    can_manage_notes = Column(Boolean, default=False)
    can_manage_filters = Column(Boolean, default=False)
    can_manage_settings = Column(Boolean, default=False)
    can_manage_locks = Column(Boolean, default=False)
    can_manage_roles = Column(Boolean, default=False)
    can_view_status = Column(Boolean, default=False)
    can_view_logs = Column(Boolean, default=False)
    granted_by = Column(BigInteger, nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="permissions")

    __table_args__ = (
        Index("uq_permissions_group_user", "group_id", "telegram_id", unique=True),
    )
    
    def __repr__(self):
        return f"<Permission(group_id={self.group_id}, telegram_id={self.telegram_id}, role={self.role})>"


class FloodTracker(Base):
    """Anti-flood tracking table."""
    __tablename__ = "flood_tracker"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    message_count = Column(Integer, default=0)
    window_start = Column(DateTime, default=datetime.utcnow)
    last_message = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="flood_records")
    
    __table_args__ = (
        Index('idx_flood_tracking', 'group_id', 'telegram_id'),
    )
    
    def __repr__(self):
        return f"<FloodTracker(group_id={self.group_id}, telegram_id={self.telegram_id}, count={self.message_count})>"


class Note(Base):
    """Notes system table - save and retrieve content."""
    __tablename__ = "notes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    note_name = Column(String, nullable=False)  # Lowercase, no spaces
    content = Column(Text, nullable=False)
    file_id = Column(String, nullable=True)  # For media notes
    file_type = Column(String, nullable=True)  # photo, video, document, etc.
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="notes")
    
    __table_args__ = (
        Index('idx_group_note', 'group_id', 'note_name', unique=True),
    )
    
    def __repr__(self):
        return f"<Note(group_id={self.group_id}, note_name={self.note_name})>"


class Filter(Base):
    """Message filters table - auto-respond or delete."""
    __tablename__ = "filters"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    keyword = Column(String, nullable=False)  # Trigger keyword
    response = Column(Text, nullable=False)  # Response text
    filter_type = Column(String, default="text")  # text, delete, warn
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="filters")
    
    __table_args__ = (
        Index('idx_group_filter', 'group_id', 'keyword'),
    )
    
    def __repr__(self):
        return f"<Filter(group_id={self.group_id}, keyword={self.keyword})>"


class AdminLog(Base):
    """Admin action logging table - track everything."""
    __tablename__ = "admin_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    admin_id = Column(BigInteger, nullable=False)  # Who did the action
    target_id = Column(BigInteger, nullable=True)  # Who was affected (if applicable)
    action = Column(String, nullable=False)  # kick, ban, warn, mute, etc.
    reason = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="admin_logs")
    
    __table_args__ = (
        Index('idx_admin_logs', 'group_id', 'timestamp'),
        Index('idx_target_logs', 'group_id', 'target_id'),
    )
    
    def __repr__(self):
        return f"<AdminLog(group_id={self.group_id}, action={self.action}, admin_id={self.admin_id})>"


class ConfigLinkToken(Base):
    """Short-lived, one-time tokens to open a group's settings panel in DM."""
    __tablename__ = "config_link_tokens"

    token = Column(String, primary_key=True)
    group_id = Column(BigInteger, nullable=False)
    admin_id = Column(BigInteger, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_cfg_token_expiry", "expires_at"),
        Index("idx_cfg_token_group_admin", "group_id", "admin_id"),
    )


class SupportLinkToken(Base):
    """Short-lived tokens to open a support/ticket intake flow in DM."""

    __tablename__ = "support_link_tokens"

    token = Column(String, primary_key=True)
    group_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_sup_token_expiry", "expires_at"),
        Index("idx_sup_token_group_user", "group_id", "user_id"),
    )


class PendingJoinVerification(Base):
    """Pending verification for a user in a specific group (global verification outcome)."""
    __tablename__ = "pending_join_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    kind = Column(String, default="post_join")  # post_join | join_request
    status = Column(String, default="pending")  # pending, approved, rejected, timed_out, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    join_request_at = Column(DateTime, nullable=True)
    user_chat_id = Column(BigInteger, nullable=True)  # Only for kind=join_request (DM window target)
    expires_at = Column(DateTime, nullable=False)
    prompt_message_id = Column(BigInteger, nullable=True)
    dm_message_id = Column(BigInteger, nullable=True)
    rules_accepted_at = Column(DateTime, nullable=True)
    captcha_kind = Column(String, nullable=True)
    captcha_expected = Column(String, nullable=True)
    captcha_attempts = Column(Integer, default=0, nullable=False)
    captcha_solved_at = Column(DateTime, nullable=True)
    mercle_session_id = Column(String, nullable=True)
    decided_by = Column(BigInteger, nullable=True)  # admin/user id who decided
    decided_at = Column(DateTime, nullable=True)

    group = relationship("Group")

    __table_args__ = (
        Index("idx_pv_group_user", "group_id", "telegram_id"),
        Index("idx_pv_status_expiry", "status", "expires_at"),
        Index("idx_pv_expires_at", "expires_at"),
        # One active pending per (group_id, telegram_id, kind) when status='pending'.
        # This is relied upon by PendingVerificationService.create_pending() for concurrency safety.
        Index(
            "uq_pv_active",
            "group_id",
            "telegram_id",
            "kind",
            unique=True,
            sqlite_where=text("status='pending'"),
            postgresql_where=text("status='pending'"),
        ),
    )


class VerificationLinkToken(Base):
    """Short-lived tokens to open the DM verification panel for a pending join verification."""
    __tablename__ = "verification_link_tokens"

    token = Column(String, primary_key=True)
    pending_id = Column(Integer, ForeignKey("pending_join_verifications.id"), nullable=False)
    group_id = Column(BigInteger, nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    pending = relationship("PendingJoinVerification")

    __table_args__ = (
        Index("idx_ver_token_expiry", "expires_at"),
        Index("idx_ver_token_pending", "pending_id"),
        Index("idx_ver_token_pending_expiry_used", "pending_id", "expires_at", "used_at"),
    )


class DmPanelState(Base):
    """Tracks persistent DM panel message IDs (single-message panels)."""
    __tablename__ = "dm_panel_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, nullable=False)
    panel_type = Column(String, nullable=False)  # home, help, settings
    group_id = Column(BigInteger, nullable=True)
    message_id = Column(BigInteger, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_dm_panel_lookup", "telegram_id", "panel_type", "group_id", unique=True),
    )


class Ticket(Base):
    """Support ticket with full conversation history."""

    __tablename__ = "tickets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    user_id = Column(BigInteger, nullable=False)
    status = Column(String, nullable=False, default="open")  # open|closed
    subject = Column(String, nullable=True)
    message = Column(Text, nullable=False)  # First message (kept for backward compat)

    # Enhanced fields
    priority = Column(String, default="normal", nullable=False)  # low|normal|high|urgent
    assigned_to = Column(BigInteger, nullable=True)
    category = Column(String, nullable=True)
    last_message_at = Column(DateTime, nullable=True)
    last_staff_reply_at = Column(DateTime, nullable=True)
    last_user_message_at = Column(DateTime, nullable=True)
    message_count = Column(Integer, default=1, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    staff_chat_id = Column(BigInteger, nullable=True)
    staff_thread_id = Column(BigInteger, nullable=True)
    staff_message_id = Column(BigInteger, nullable=True)

    group = relationship("Group")
    messages = relationship("TicketMessage", back_populates="ticket", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_ticket_group_status", "group_id", "status", "created_at"),
        Index("idx_ticket_user", "user_id", "created_at"),
        Index("idx_ticket_priority", "priority", "status"),
        Index("idx_ticket_assigned", "assigned_to", "status"),
    )


class TicketMessage(Base):
    """Individual messages within a ticket conversation."""

    __tablename__ = "ticket_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id = Column(BigInteger, ForeignKey("tickets.id"), nullable=False)
    sender_type = Column(String, nullable=False)  # user|staff|system
    sender_id = Column(BigInteger, nullable=True)  # Telegram user ID
    sender_name = Column(String, nullable=True)  # Display name
    message_type = Column(String, nullable=False, default="text")  # text|photo|video|document|etc
    content = Column(Text, nullable=True)  # Text content
    file_id = Column(String, nullable=True)  # Telegram file_id for media
    telegram_message_id = Column(BigInteger, nullable=True)  # Original message ID
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="messages")

    __table_args__ = (
        Index("idx_ticket_msg_ticket", "ticket_id", "created_at"),
        Index("idx_ticket_msg_sender", "sender_id", "created_at"),
    )


class TicketUserState(Base):
    """Tracks the user's currently active ticket (for DM → staff relay)."""

    __tablename__ = "ticket_user_state"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    ticket_id = Column(BigInteger, ForeignKey("tickets.id"), nullable=False)
    creating_ticket = Column(Boolean, default=False, nullable=False)  # Lock during creation
    last_message_at = Column(DateTime, nullable=True)  # For deduplication
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    ticket = relationship("Ticket")

    __table_args__ = (
        Index("idx_ticket_user_state_ticket", "ticket_id"),
    )


class GroupWizardState(Base):
    """Stores one-time setup wizard state for a group."""
    __tablename__ = "group_wizard_state"

    group_id = Column(BigInteger, ForeignKey("groups.group_id"), primary_key=True)
    wizard_completed = Column(Boolean, default=False)
    wizard_step = Column(Integer, default=1)  # 1 preset, 2 verification, 3 logs
    setup_card_message_id = Column(BigInteger, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    group = relationship("Group")


class GroupUserState(Base):
    """Per-group attribution/history (not per-group verification)."""
    __tablename__ = "group_user_state"

    group_id = Column(BigInteger, ForeignKey("groups.group_id"), primary_key=True)
    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    username_lc = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    last_source = Column(String, nullable=True)  # join | dm_verify | message | other
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    join_count = Column(Integer, default=1)
    first_verified_seen_at = Column(DateTime, nullable=True)
    last_verification_session_id = Column(String, nullable=True)

    group = relationship("Group")

    __table_args__ = (
        Index("idx_group_user_username", "group_id", "username_lc"),
    )


class MetricCounter(Base):
    """Small persistent counters (used for bot operational metrics)."""

    __tablename__ = "metric_counters"

    key = Column(String, primary_key=True)
    value = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Job(Base):
    """DB-backed job queue entries (used for broadcasts, sequences, tickets)."""

    __tablename__ = "jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_type = Column(String, nullable=False)  # e.g. "broadcast_send"
    status = Column(String, nullable=False, default="pending")  # pending|running|done|failed|cancelled
    run_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    attempts = Column(Integer, nullable=False, default=0)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(String, nullable=True)
    payload = Column(Text, nullable=False, default="{}")  # JSON string (avoid dialect-specific JSON type)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_jobs_due", "status", "run_at"),
    )


class Broadcast(Base):
    """Broadcast campaign definition + progress tracking."""

    __tablename__ = "broadcasts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    scheduled_at = Column(DateTime, nullable=True)

    status = Column(String, nullable=False, default="pending")  # pending|running|completed|failed|cancelled
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    text = Column(Text, nullable=False)
    parse_mode = Column(String, nullable=True)  # "Markdown"|"HTML"|None
    disable_web_page_preview = Column(Boolean, default=True)

    total_targets = Column(Integer, nullable=False, default=0)
    sent_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    targets = relationship("BroadcastTarget", back_populates="broadcast")


class BroadcastTarget(Base):
    """Broadcast delivery target (chat or user)."""

    __tablename__ = "broadcast_targets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    broadcast_id = Column(BigInteger, ForeignKey("broadcasts.id"), nullable=False)
    chat_id = Column(BigInteger, nullable=False)

    status = Column(String, nullable=False, default="pending")  # pending|sent|failed
    telegram_message_id = Column(BigInteger, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    broadcast = relationship("Broadcast", back_populates="targets")

    __table_args__ = (
        Index("idx_broadcast_target_status", "broadcast_id", "status"),
    )


class Sequence(Base):
    """Message sequence (drip/onboarding) definition."""

    __tablename__ = "sequences"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    key = Column(String, nullable=False)  # stable identifier, e.g. "onboarding_verified"
    name = Column(String, nullable=False)
    trigger = Column(String, nullable=False)  # e.g. "user_verified"
    enabled = Column(Boolean, default=True)
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    group = relationship("Group", back_populates="sequences")
    steps = relationship("SequenceStep", back_populates="sequence")
    runs = relationship("SequenceRun", back_populates="sequence")

    __table_args__ = (
        Index("uq_sequence_key", "group_id", "key", unique=True),
        Index("idx_sequence_trigger", "group_id", "trigger", "enabled"),
    )


class SequenceStep(Base):
    """A single step in a sequence."""

    __tablename__ = "sequence_steps"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sequence_id = Column(BigInteger, ForeignKey("sequences.id"), nullable=False)
    step_order = Column(Integer, nullable=False, default=1)
    delay_seconds = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False)
    parse_mode = Column(String, nullable=True)  # "Markdown"|"HTML"|None
    disable_web_page_preview = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sequence = relationship("Sequence", back_populates="steps")

    __table_args__ = (
        Index("uq_sequence_step_order", "sequence_id", "step_order", unique=True),
    )


class SequenceRun(Base):
    """A single execution of a sequence for a user."""

    __tablename__ = "sequence_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sequence_id = Column(BigInteger, ForeignKey("sequences.id"), nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    trigger_key = Column(String, nullable=True)  # used for idempotency per trigger/event
    status = Column(String, nullable=False, default="running")  # running|completed|failed|cancelled
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    sequence = relationship("Sequence", back_populates="runs")
    steps = relationship("SequenceRunStep", back_populates="run")

    __table_args__ = (
        Index("idx_sequence_run_user", "sequence_id", "telegram_id"),
        Index("uq_sequence_run_trigger", "sequence_id", "telegram_id", "trigger_key", unique=True),
    )


class SequenceRunStep(Base):
    """Per-step delivery status for a run."""

    __tablename__ = "sequence_run_steps"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("sequence_runs.id"), nullable=False)
    step_id = Column(BigInteger, ForeignKey("sequence_steps.id"), nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending|sent|failed|cancelled
    run_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    attempts = Column(Integer, nullable=False, default=0)
    sent_at = Column(DateTime, nullable=True)
    telegram_message_id = Column(BigInteger, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("SequenceRun", back_populates="steps")
    step = relationship("SequenceStep")

    __table_args__ = (
        Index("uq_run_step", "run_id", "step_id", unique=True),
        Index("idx_run_step_due", "status", "run_at"),
    )


class Rule(Base):
    """Rules engine: triggers + conditions + actions."""

    __tablename__ = "rules"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    name = Column(String, nullable=False, default="Rule")
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, nullable=False, default=100)  # lower runs first
    trigger = Column(String, nullable=False, default="message_group")  # message_group|dm_message|...
    stop_processing = Column(Boolean, default=True)

    match_type = Column(String, nullable=False, default="contains")  # contains|regex
    pattern = Column(Text, nullable=False)
    case_sensitive = Column(Boolean, default=False)

    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    group = relationship("Group")
    actions = relationship("RuleAction", back_populates="rule")

    __table_args__ = (
        Index("idx_rules_lookup", "group_id", "trigger", "enabled", "priority"),
    )


class RuleAction(Base):
    """Ordered actions for a rule (reply/delete/warn/mute/etc)."""

    __tablename__ = "rule_actions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_id = Column(BigInteger, ForeignKey("rules.id"), nullable=False)
    action_order = Column(Integer, nullable=False, default=1)
    action_type = Column(String, nullable=False)  # reply|delete|warn|mute|log|start_sequence|create_ticket
    params = Column(Text, nullable=False, default="{}")  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

    rule = relationship("Rule", back_populates="actions")

    __table_args__ = (
        Index("uq_rule_action_order", "rule_id", "action_order", unique=True),
    )
