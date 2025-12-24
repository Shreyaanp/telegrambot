"""Add from_mini_app column to verification_sessions

Revision ID: add_from_mini_app
Revises: 
Create Date: 2024-12-20
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_from_mini_app'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add from_mini_app column with default False
    op.add_column('verification_sessions', 
                  sa.Column('from_mini_app', sa.Boolean(), nullable=True, server_default='false'))


def downgrade() -> None:
    op.drop_column('verification_sessions', 'from_mini_app')
