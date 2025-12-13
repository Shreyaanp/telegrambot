"""Database connection and session management."""
import logging
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from database.models import Base

logger = logging.getLogger(__name__)


class Database:
    """Database manager for SQLite."""
    
    def __init__(self, database_url: str = "sqlite+aiosqlite:///bot.db"):
        """Initialize database connection."""
        self.database_url = database_url
        self.engine = create_async_engine(
            database_url,
            echo=False,
            poolclass=NullPool,
        )
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    async def create_tables(self):
        """Create all database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    
    @asynccontextmanager
    async def session(self) -> AsyncSession:
        """Get a database session."""
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    async def close(self):
        """Close database connections."""
        await self.engine.dispose()
        logger.info("Database connections closed")


# Global database instance
db = Database()

