"""add raid mode and ticket bridge

Revision ID: e1c9a8b7d6f5
Revises: b0f1d6f5b8e2
Create Date: 2025-12-18 17:05:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "e1c9a8b7d6f5"
down_revision = "b0f1d6f5b8e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("raid_mode_until", sa.DateTime(), nullable=True))

    op.create_table(
        "ticket_user_state",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("idx_ticket_user_state_ticket", "ticket_user_state", ["ticket_id"], unique=False)

    op.create_index("idx_ticket_staff_thread", "tickets", ["staff_chat_id", "staff_thread_id"], unique=False)
    op.create_index("idx_ticket_staff_message", "tickets", ["staff_chat_id", "staff_message_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_ticket_staff_message", table_name="tickets")
    op.drop_index("idx_ticket_staff_thread", table_name="tickets")

    op.drop_index("idx_ticket_user_state_ticket", table_name="ticket_user_state")
    op.drop_table("ticket_user_state")

    op.drop_column("groups", "raid_mode_until")

