"""Database connection and session management."""
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from database.models import Base
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Ensure `.env` is loaded even when database module is imported before `bot.config`.
load_dotenv()


class Database:
    """Database connection manager."""
    
    def __init__(self, database_url: str | None = None):
        """Initialize database connection."""
        # Production uses Postgres (asyncpg). We intentionally do not default to SQLite.
        # Keep import-time safe; validate on connect().
        self.database_url = database_url or os.getenv("DATABASE_URL") or ""
        self.engine = None
        self.session_factory = None
        
    async def connect(self):
        """Connect to database."""
        if self.engine is not None and self.session_factory is not None:
            return

        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL is required (expected e.g. postgresql+asyncpg://user:pass@host:5432/dbname)"
            )

        logger.info(f"Connecting to database: {_redact_url(self.database_url)}")

        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
        )
        
        # Create session factory
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        logger.info("Database connection established")
    
    async def create_tables(self):
        """Create all database tables (development convenience)."""
        if self.engine is None:
            await self.connect()

        logger.info("Creating database tables...")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        logger.info("Database tables created successfully")

    async def require_schema(self) -> None:
        """
        Ensure the database schema exists.

        Production expects schema migrations to be applied via Alembic (out of band):
            `alembic upgrade head`
        """
        if self.engine is None:
            await self.connect()

        try:
            async with self.session() as session:
                await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        except Exception as e:
            raise RuntimeError(
                "Database schema is not initialized. Run `alembic upgrade head` against DATABASE_URL."
            ) from e
    
    async def drop_tables(self):
        """Drop all database tables (use with caution!)."""
        logger.warning("Dropping all database tables...")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("Database tables dropped")
    
    async def disconnect(self):
        """Disconnect from database."""
        if self.engine:
            logger.info("Disconnecting from database...")
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            logger.info("Database disconnected")

    async def close(self):
        """Alias for disconnect() (kept for compatibility with existing call sites)."""
        await self.disconnect()
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Provide a transactional scope for database operations.
        
        Usage:
            async with db.session() as session:
                user = await session.get(User, telegram_id)
                session.add(user)
                await session.commit()
        """
        if not self.session_factory:
            await self.connect()
        
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}", exc_info=True)
                raise
            finally:
                await session.close()
    
    async def get_session(self) -> AsyncSession:
        """
        Get a new database session (manual management).
        
        Note: Caller is responsible for closing the session.
        Prefer using the session() context manager instead.
        """
        if not self.session_factory:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self.session_factory()
    
    async def health_check(self) -> bool:
        """Check if database is accessible."""
        try:
            async with self.session() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def get_table_counts(self) -> dict:
        """Get row counts for all tables (for debugging/monitoring)."""
        counts = {}
        try:
            async with self.session() as session:
                from database.models import (
                    User, Group, GroupMember, VerificationSession,
                    Warning, Whitelist, Permission, FloodTracker
                )
                
                for model in [User, Group, GroupMember, VerificationSession,
                             Warning, Whitelist, Permission, FloodTracker]:
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {model.__tablename__}"))
                    counts[model.__tablename__] = result.scalar()
        except Exception as e:
            logger.error(f"Failed to get table counts: {e}")
        
        return counts

# Single shared DB handle used across the app.
db = Database()


def _redact_url(url: str) -> str:
    # Redact credentials in logs: scheme://user:pass@host -> scheme://user:***@host
    try:
        if "://" not in url or "@" not in url:
            return url
        left, right = url.split("@", 1)
        if ":" not in left:
            return url
        prefix, _ = left.rsplit(":", 1)
        return f"{prefix}:***@{right}"
    except Exception:
        return "<redacted>"
