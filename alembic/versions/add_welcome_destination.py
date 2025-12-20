"""add welcome destination

Revision ID: add_welcome_destination
Revises: 7607fe8aa75e
Create Date: 2024-12-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_welcome_destination'
down_revision = '7607fe8aa75e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add welcome_destination column with default value 'group'
    op.add_column('groups', sa.Column('welcome_destination', sa.String(), nullable=False, server_default='group'))


def downgrade() -> None:
    # Remove welcome_destination column
    op.drop_column('groups', 'welcome_destination')
