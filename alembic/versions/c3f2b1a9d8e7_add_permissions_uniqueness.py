"""Add uniqueness for permissions (group_id, telegram_id).

Revision ID: c3f2b1a9d8e7
Revises: 244474fb5898
Create Date: 2025-12-18
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3f2b1a9d8e7"
down_revision = "244474fb5898"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # If duplicates exist (shouldn't, but can happen due to older bugs), keep the newest row.
    op.execute(
        """
        DELETE FROM permissions a
        USING permissions b
        WHERE a.group_id = b.group_id
          AND a.telegram_id = b.telegram_id
          AND a.id < b.id;
        """
    )
    op.create_index(
        "uq_permissions_group_user",
        "permissions",
        ["group_id", "telegram_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_permissions_group_user", table_name="permissions")

