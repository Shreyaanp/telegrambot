"""Database models - Complete schema for full-featured bot."""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index, BigInteger
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Verified users table - global verification across all groups."""
    __tablename__ = "users"
    
    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    mercle_user_id = Column(String, nullable=False, unique=True)
    verified_at = Column(DateTime, default=datetime.utcnow)
    is_banned = Column(Boolean, default=False)  # Global ban
    
    # Relationships
    memberships = relationship("GroupMember", back_populates="user")
    
    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"


class Group(Base):
    """Group settings table - per-group configuration."""
    __tablename__ = "groups"
    
    group_id = Column(BigInteger, primary_key=True)
    group_name = Column(String, nullable=True)
    
    # Verification settings
    verification_enabled = Column(Boolean, default=True)
    verification_timeout = Column(Integer, default=300)  # 5 minutes
    kick_unverified = Column(Boolean, default=True)
    
    # Welcome/Goodbye
    welcome_enabled = Column(Boolean, default=True)
    welcome_message = Column(Text, nullable=True)
    goodbye_enabled = Column(Boolean, default=False)
    goodbye_message = Column(Text, nullable=True)
    
    # Moderation settings
    warn_limit = Column(Integer, default=3)  # Kick after X warns
    antiflood_enabled = Column(Boolean, default=True)
    antiflood_limit = Column(Integer, default=10)  # Messages per minute
    lock_links = Column(Boolean, default=False)
    lock_media = Column(Boolean, default=False)
    
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
    granted_by = Column(BigInteger, nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="permissions")
    
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


class PendingJoinVerification(Base):
    """Pending verification for a user in a specific group (global verification outcome)."""
    __tablename__ = "pending_join_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(BigInteger, nullable=False)
    status = Column(String, default="pending")  # pending, approved, rejected, timed_out, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    prompt_message_id = Column(BigInteger, nullable=True)
    dm_message_id = Column(BigInteger, nullable=True)
    mercle_session_id = Column(String, nullable=True)
    decided_by = Column(BigInteger, nullable=True)  # admin/user id who decided
    decided_at = Column(DateTime, nullable=True)

    group = relationship("Group")

    __table_args__ = (
        Index("idx_pv_group_user", "group_id", "telegram_id"),
        Index("idx_pv_status_expiry", "status", "expires_at"),
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
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    join_count = Column(Integer, default=1)
    first_verified_seen_at = Column(DateTime, nullable=True)
    last_verification_session_id = Column(String, nullable=True)

    group = relationship("Group")
