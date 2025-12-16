"""Database connection and session management with WAL mode optimizations."""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import event, text
from database.models import Base

logger = logging.getLogger(__name__)


class Database:
    """Database connection manager with SQLite WAL mode optimizations."""
    
    def __init__(self, database_url: str = "sqlite+aiosqlite:///bot_db.sqlite"):
        """Initialize database connection."""
        self.database_url = database_url
        self.engine = None
        self.session_factory = None
        
    async def connect(self):
        """Connect to database and enable WAL mode."""
        logger.info(f"Connecting to database: {self.database_url}")
        
        # Create async engine with optimizations
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,  # Verify connections before using
            connect_args={
                "check_same_thread": False,
            }
        )
        
        # Enable WAL mode and optimizations
        @event.listens_for(self.engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            # Enable WAL mode for concurrent reads/writes
            cursor.execute("PRAGMA journal_mode=WAL")
            # Normal synchronous mode for better performance
            cursor.execute("PRAGMA synchronous=NORMAL")
            # 64MB cache size for better performance
            cursor.execute("PRAGMA cache_size=-64000")
            # Store temp tables in memory
            cursor.execute("PRAGMA temp_store=MEMORY")
            # Wait up to 5 seconds on database locks
            cursor.execute("PRAGMA busy_timeout=5000")
            # Enable foreign key constraints
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
            logger.debug("SQLite WAL mode and optimizations enabled")
        
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
        """Create all database tables."""
        logger.info("Creating database tables...")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        logger.info("Database tables created successfully")
    
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
            logger.info("Database disconnected")
    
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
            raise RuntimeError("Database not connected. Call connect() first.")
        
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


# Global database instance
_db_instance: Database = None


def get_database() -> Database:
    """Get the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


async def init_database(database_url: str = "sqlite+aiosqlite:///bot_db.sqlite"):
    """Initialize the global database instance."""
    global _db_instance
    _db_instance = Database(database_url)
    await _db_instance.connect()
    await _db_instance.create_tables()
    return _db_instance


async def close_database():
    """Close the global database instance."""
    global _db_instance
    if _db_instance:
        await _db_instance.disconnect()
        _db_instance = None


# Create a simple wrapper class for backward compatibility
class DatabaseWrapper:
    """Wrapper to provide 'db' global instance for backward compatibility."""
    
    def __init__(self):
        self._db = None
    
    def _get_db(self):
        if self._db is None:
            self._db = get_database()
        return self._db
    
    async def create_tables(self):
        """Create database tables."""
        db = self._get_db()
        if db.engine is None:
            await db.connect()
        await db.create_tables()
    
    async def close(self):
        """Close database connection."""
        await close_database()
        self._db = None
    
    def session(self):
        """Get database session context manager."""
        return self._get_db().session()


# Global 'db' instance for backward compatibility
db = DatabaseWrapper()
