"""merge_heads

Revision ID: b6ad232558bc
Revises: add_from_mini_app, add_rule_warnings
Create Date: 2025-12-20 15:42:25.954097

"""

from alembic import op
import sqlalchemy as sa



revision = 'b6ad232558bc'
down_revision = ('add_from_mini_app', 'add_rule_warnings')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

