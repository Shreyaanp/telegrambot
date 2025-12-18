"""add broadcast scheduling

Revision ID: 1604c0e0ca30
Revises: b45e1a42878a
Create Date: 2025-12-18 08:51:23.586202

"""

from alembic import op
import sqlalchemy as sa



revision = '1604c0e0ca30'
down_revision = 'b45e1a42878a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('broadcasts', sa.Column('scheduled_at', sa.DateTime(), nullable=True))
    op.create_index('idx_broadcasts_scheduled_at', 'broadcasts', ['scheduled_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_broadcasts_scheduled_at', table_name='broadcasts')
    op.drop_column('broadcasts', 'scheduled_at')
