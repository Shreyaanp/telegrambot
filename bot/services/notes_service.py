"""Notes service - save and retrieve group notes."""
import logging
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, and_, delete

from database.db import db
from database.models import Note

logger = logging.getLogger(__name__)


class NotesService:
    """
    Notes management service.
    
    Save and retrieve notes with hashtag support.
    """
    
    async def save_note(
        self,
        group_id: int,
        note_name: str,
        content: str,
        admin_id: int,
        file_id: Optional[str] = None,
        file_type: Optional[str] = None
    ) -> bool:
        """
        Save or update a note.
        
        Args:
            group_id: Group ID
            note_name: Note name (lowercase, no spaces)
            content: Note content
            admin_id: Admin saving the note
            file_id: Optional file ID for media
            file_type: Optional file type
            
        Returns:
            True if successful
        """
        async with db.session() as session:
            # Normalize note name
            note_name = note_name.lower().replace(" ", "_")
            
            # Check if note exists
            result = await session.execute(
                select(Note)
                .where(
                    and_(
                        Note.group_id == group_id,
                        Note.note_name == note_name
                    )
                )
            )
            note = result.scalar_one_or_none()
            
            if note:
                # Update existing note
                note.content = content
                note.file_id = file_id
                note.file_type = file_type
                note.updated_at = datetime.utcnow()
            else:
                # Create new note
                note = Note(
                    group_id=group_id,
                    note_name=note_name,
                    content=content,
                    file_id=file_id,
                    file_type=file_type,
                    created_by=admin_id,
                    created_at=datetime.utcnow()
                )
                session.add(note)
            
            await session.commit()
            logger.info(f"Note '{note_name}' saved in group {group_id}")
            return True
    
    async def get_note(self, group_id: int, note_name: str) -> Optional[Note]:
        """
        Get a note by name.
        
        Args:
            group_id: Group ID
            note_name: Note name
            
        Returns:
            Note object or None
        """
        async with db.session() as session:
            note_name = note_name.lower().replace(" ", "_")
            
            result = await session.execute(
                select(Note)
                .where(
                    and_(
                        Note.group_id == group_id,
                        Note.note_name == note_name
                    )
                )
            )
            return result.scalar_one_or_none()
    
    async def delete_note(self, group_id: int, note_name: str) -> bool:
        """
        Delete a note.
        
        Args:
            group_id: Group ID
            note_name: Note name
            
        Returns:
            True if deleted, False if not found
        """
        async with db.session() as session:
            note_name = note_name.lower().replace(" ", "_")
            
            result = await session.execute(
                delete(Note)
                .where(
                    and_(
                        Note.group_id == group_id,
                        Note.note_name == note_name
                    )
                )
            )
            await session.commit()
            
            deleted = result.rowcount > 0
            if deleted:
                logger.info(f"Note '{note_name}' deleted from group {group_id}")
            return deleted
    
    async def list_notes(self, group_id: int) -> List[Note]:
        """
        List all notes in a group.
        
        Args:
            group_id: Group ID
            
        Returns:
            List of Note objects
        """
        async with db.session() as session:
            result = await session.execute(
                select(Note)
                .where(Note.group_id == group_id)
                .order_by(Note.note_name)
            )
            return list(result.scalars().all())

