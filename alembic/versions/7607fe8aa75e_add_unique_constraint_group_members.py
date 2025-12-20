"""add_unique_constraint_group_members

Revision ID: 7607fe8aa75e
Revises: fc0a5d826c47
Create Date: 2025-12-20 00:41:30.455195

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = '7607fe8aa75e'
down_revision = 'fc0a5d826c47'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First, remove any duplicate entries (keep the one with the highest id)
    conn = op.get_bind()
    conn.execute(text("""
        DELETE FROM group_members gm1
        USING group_members gm2
        WHERE gm1.id < gm2.id
        AND gm1.group_id = gm2.group_id
        AND gm1.telegram_id = gm2.telegram_id
    """))
    
    # Now add the unique constraint
    op.create_unique_constraint(
        'uq_group_members_group_telegram',
        'group_members',
        ['group_id', 'telegram_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_group_members_group_telegram', 'group_members', type_='unique')

