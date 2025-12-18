"""add silent automations

Revision ID: b0f1d6f5b8e2
Revises: 9253c91911b1
Create Date: 2025-12-18 16:50:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "b0f1d6f5b8e2"
down_revision = "9253c91911b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column("silent_automations", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("groups", "silent_automations")

