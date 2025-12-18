"""add rules acceptance and captcha

Revision ID: b6c44018d3e5
Revises: e1c9a8b7d6f5
Create Date: 2025-12-18 17:47:41.029833

"""

from alembic import op
import sqlalchemy as sa



revision = 'b6c44018d3e5'
down_revision = 'e1c9a8b7d6f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column("require_rules_acceptance", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "groups",
        sa.Column("captcha_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "groups",
        sa.Column("captcha_style", sa.String(), nullable=False, server_default=sa.text("'button'")),
    )
    op.add_column(
        "groups",
        sa.Column("captcha_max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
    )

    op.add_column("pending_join_verifications", sa.Column("rules_accepted_at", sa.DateTime(), nullable=True))
    op.add_column("pending_join_verifications", sa.Column("captcha_kind", sa.String(), nullable=True))
    op.add_column("pending_join_verifications", sa.Column("captcha_expected", sa.String(), nullable=True))
    op.add_column(
        "pending_join_verifications",
        sa.Column("captcha_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("pending_join_verifications", sa.Column("captcha_solved_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("pending_join_verifications", "captcha_solved_at")
    op.drop_column("pending_join_verifications", "captcha_attempts")
    op.drop_column("pending_join_verifications", "captcha_expected")
    op.drop_column("pending_join_verifications", "captcha_kind")
    op.drop_column("pending_join_verifications", "rules_accepted_at")

    op.drop_column("groups", "captcha_max_attempts")
    op.drop_column("groups", "captcha_style")
    op.drop_column("groups", "captcha_enabled")
    op.drop_column("groups", "require_rules_acceptance")
