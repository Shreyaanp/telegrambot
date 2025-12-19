"""add_verified_until_to_users

Revision ID: 282cf9249b8b
Revises: d4f0c2a6f1b3
Create Date: 2025-12-19 10:11:04.167016

"""

from alembic import op
import sqlalchemy as sa



revision = '282cf9249b8b'
down_revision = 'd4f0c2a6f1b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add verified_until column to users table
    op.add_column('users', sa.Column('verified_until', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove verified_until column from users table
    op.drop_column('users', 'verified_until')

