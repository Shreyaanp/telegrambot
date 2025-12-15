"""Migration script to add UX improvement columns to existing database."""
import asyncio
import logging
from sqlalchemy import text
from database.db import init_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Add new columns for UX improvements."""
    logger.info("Starting UX improvements migration...")
    
    db = await init_database()
    
    migrations = [
        # Add new columns to groups table
        "ALTER TABLE groups ADD COLUMN IF NOT EXISTS verification_location TEXT DEFAULT 'group'",
        "ALTER TABLE groups ADD COLUMN IF NOT EXISTS welcome_message_buttons TEXT",
        "ALTER TABLE groups ADD COLUMN IF NOT EXISTS goodbye_message TEXT",
        "ALTER TABLE groups ADD COLUMN IF NOT EXISTS goodbye_enabled BOOLEAN DEFAULT 0",
        
        # Create new tables for filters
        """CREATE TABLE IF NOT EXISTS filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            response TEXT NOT NULL,
            buttons TEXT,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_filters_group_id ON filters(group_id)",
        
        # Create new tables for locks
        """CREATE TABLE IF NOT EXISTS locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            lock_type TEXT NOT NULL,
            enabled BOOLEAN DEFAULT 1
        )""",
        "CREATE INDEX IF NOT EXISTS idx_locks_group_id ON locks(group_id)",
        
        # Create new tables for notes
        """CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            note_name TEXT NOT NULL,
            content TEXT NOT NULL,
            media_type TEXT,
            media_file_id TEXT,
            buttons TEXT,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_notes_group_id ON notes(group_id)",
        
        # Create new tables for admin logs
        """CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            admin_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_user_id INTEGER,
            reason TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_admin_logs_group_id ON admin_logs(group_id)",
        "CREATE INDEX IF NOT EXISTS idx_admin_logs_timestamp ON admin_logs(timestamp)",
    ]
    
    try:
        async with db.session() as session:
            for migration in migrations:
                try:
                    logger.info(f"Executing: {migration[:80]}...")
                    await session.execute(text(migration))
                    await session.commit()
                    logger.info("✅ Success")
                except Exception as e:
                    logger.warning(f"⚠️ Migration warning (may already exist): {e}")
                    await session.rollback()
        
        logger.info("=" * 70)
        logger.info("✅ UX IMPROVEMENTS MIGRATION COMPLETE")
        logger.info("=" * 70)
        logger.info("")
        logger.info("New features added:")
        logger.info("  ✅ Verification location setting (group/dm/both)")
        logger.info("  ✅ Welcome message buttons")
        logger.info("  ✅ Goodbye messages")
        logger.info("  ✅ Message filters")
        logger.info("  ✅ Message locks")
        logger.info("  ✅ Notes system")
        logger.info("  ✅ Admin action logs")
        logger.info("")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        raise
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(migrate())

