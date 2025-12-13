"""Database models for the verification bot."""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Verified users table."""
    __tablename__ = "users"
    
    telegram_id = Column(Integer, primary_key=True)
    username = Column(String, nullable=True)
    mercle_user_id = Column(String, nullable=False, unique=True)
    verified_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to sessions
    sessions = relationship("VerificationSession", back_populates="user")
    
    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"


class VerificationSession(Base):
    """Active verification sessions table."""
    __tablename__ = "verification_sessions"
    
    session_id = Column(String, primary_key=True)
    telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    telegram_username = Column(String, nullable=True)
    group_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String, default="pending")  # pending, approved, rejected, expired
    
    # Relationship to user
    user = relationship("User", back_populates="sessions")
    
    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() > self.expires_at
    
    def __repr__(self):
        return f"<VerificationSession(session_id={self.session_id}, status={self.status})>"


class GroupSettings(Base):
    """Group-specific settings table."""
    __tablename__ = "group_settings"
    
    group_id = Column(Integer, primary_key=True)
    group_name = Column(String, nullable=True)
    verification_required = Column(Boolean, default=True)
    timeout_seconds = Column(Integer, default=30)
    added_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<GroupSettings(group_id={self.group_id}, group_name={self.group_name})>"

