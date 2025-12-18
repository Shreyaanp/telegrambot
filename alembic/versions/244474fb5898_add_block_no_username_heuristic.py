"""add block_no_username heuristic

Revision ID: 244474fb5898
Revises: 8f804c73c124
Create Date: 2025-12-18 18:11:09.930821

"""

from alembic import op
import sqlalchemy as sa



revision = '244474fb5898'
down_revision = '8f804c73c124'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column("block_no_username", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("groups", "block_no_username")
