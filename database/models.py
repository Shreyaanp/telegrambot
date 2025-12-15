"""Database models for the Rose-style verification bot."""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Verified users table - global verification across all groups."""
    __tablename__ = "users"
    
    telegram_id = Column(Integer, primary_key=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    mercle_user_id = Column(String, nullable=False, unique=True)
    verified_at = Column(DateTime, default=datetime.utcnow)
    global_reputation = Column(Integer, default=0)  # For future federation features
    
    # Relationships
    sessions = relationship("VerificationSession", back_populates="user")
    memberships = relationship("GroupMember", back_populates="user")
    warnings = relationship("Warning", back_populates="user")
    whitelist_entries = relationship("Whitelist", back_populates="user")
    permissions = relationship("Permission", back_populates="user")
    flood_records = relationship("FloodTracker", back_populates="user")
    
    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"


class Group(Base):
    """Group settings table - per-group configuration."""
    __tablename__ = "groups"
    
    group_id = Column(Integer, primary_key=True)
    group_name = Column(String, nullable=True)
    verification_enabled = Column(Boolean, default=True)
    auto_verify_on_join = Column(Boolean, default=True)
    verification_timeout = Column(Integer, default=120)  # seconds
    kick_on_timeout = Column(Boolean, default=True)
    verification_location = Column(String, default="group")  # group, dm, or both
    welcome_message = Column(Text, nullable=True)
    welcome_message_buttons = Column(Text, nullable=True)  # JSON for buttons
    goodbye_message = Column(Text, nullable=True)
    goodbye_enabled = Column(Boolean, default=False)
    rules_text = Column(Text, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    members = relationship("GroupMember", back_populates="group")
    sessions = relationship("VerificationSession", back_populates="group")
    warnings = relationship("Warning", back_populates="group")
    whitelist_entries = relationship("Whitelist", back_populates="group")
    permissions = relationship("Permission", back_populates="group")
    flood_records = relationship("FloodTracker", back_populates="group")
    
    def __repr__(self):
        return f"<Group(group_id={self.group_id}, group_name={self.group_name})>"


class GroupMember(Base):
    """Group membership tracking table."""
    __tablename__ = "group_members"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    verified = Column(Boolean, default=False)
    muted = Column(Boolean, default=False)
    
    # Relationships
    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="memberships")
    
    # Composite index for fast lookups
    __table_args__ = (
        Index('idx_group_member', 'group_id', 'telegram_id'),
    )
    
    def __repr__(self):
        return f"<GroupMember(group_id={self.group_id}, telegram_id={self.telegram_id})>"


class VerificationSession(Base):
    """Active verification sessions table."""
    __tablename__ = "verification_sessions"
    
    session_id = Column(String, primary_key=True)
    telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.group_id"), nullable=True)
    chat_id = Column(Integer, nullable=False)  # Where verification message was sent
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String, default="pending")  # pending, approved, rejected, expired
    message_ids = Column(Text, nullable=True)  # JSON array of message IDs to delete
    trigger_type = Column(String, default="manual")  # auto_join or manual_command
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    group = relationship("Group", back_populates="sessions")
    
    # Index for fast status lookups
    __table_args__ = (
        Index('idx_telegram_status', 'telegram_id', 'status'),
    )
    
    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() > self.expires_at
    
    def __repr__(self):
        return f"<VerificationSession(session_id={self.session_id}, status={self.status})>"


class Warning(Base):
    """Warning system table - track user warnings."""
    __tablename__ = "warnings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    warned_by = Column(Integer, nullable=False)  # Admin telegram_id
    reason = Column(Text, nullable=True)
    warned_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="warnings")
    user = relationship("User", back_populates="warnings")
    
    # Index for fast warning count lookups
    __table_args__ = (
        Index('idx_group_user_warnings', 'group_id', 'telegram_id'),
    )
    
    def __repr__(self):
        return f"<Warning(group_id={self.group_id}, telegram_id={self.telegram_id})>"


class Whitelist(Base):
    """Whitelist table - users who bypass verification."""
    __tablename__ = "whitelist"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    added_by = Column(Integer, nullable=False)  # Admin telegram_id
    reason = Column(Text, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="whitelist_entries")
    user = relationship("User", back_populates="whitelist_entries")
    
    # Index for fast whitelist checks
    __table_args__ = (
        Index('idx_group_user_whitelist', 'group_id', 'telegram_id'),
    )
    
    def __repr__(self):
        return f"<Whitelist(group_id={self.group_id}, telegram_id={self.telegram_id})>"


class Permission(Base):
    """Permissions table - custom admin roles and permissions."""
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    role = Column(String, default="moderator")  # owner, admin, moderator
    can_verify = Column(Boolean, default=False)
    can_kick = Column(Boolean, default=False)
    can_ban = Column(Boolean, default=False)
    can_warn = Column(Boolean, default=False)
    can_settings = Column(Boolean, default=False)
    granted_by = Column(Integer, nullable=False)  # Admin telegram_id
    granted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="permissions")
    user = relationship("User", back_populates="permissions")
    
    def __repr__(self):
        return f"<Permission(group_id={self.group_id}, telegram_id={self.telegram_id}, role={self.role})>"


class FloodTracker(Base):
    """Anti-flood tracking table - message rate limiting."""
    __tablename__ = "flood_tracker"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.group_id"), nullable=False)
    telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    message_count = Column(Integer, default=0)
    window_start = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("Group", back_populates="flood_records")
    user = relationship("User", back_populates="flood_records")
    
    def __repr__(self):
        return f"<FloodTracker(group_id={self.group_id}, telegram_id={self.telegram_id}, count={self.message_count})>"
