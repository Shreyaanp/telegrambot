"""Add antiflood mute duration setting.

Revision ID: d4f0c2a6f1b3
Revises: c3f2b1a9d8e7
Create Date: 2025-12-18
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d4f0c2a6f1b3"
down_revision = "c3f2b1a9d8e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column(
            "antiflood_mute_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("300"),
        ),
    )


def downgrade() -> None:
    op.drop_column("groups", "antiflood_mute_seconds")

