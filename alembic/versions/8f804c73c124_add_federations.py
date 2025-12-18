"""add federations

Revision ID: 8f804c73c124
Revises: b6c44018d3e5
Create Date: 2025-12-18 17:58:46.526858

"""

from alembic import op
import sqlalchemy as sa



revision = '8f804c73c124'
down_revision = 'b6c44018d3e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "federations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.add_column("groups", sa.Column("federation_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_groups_federation_id",
        source_table="groups",
        referent_table="federations",
        local_cols=["federation_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_groups_federation", "groups", ["federation_id"], unique=False)

    op.create_table(
        "federation_bans",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("federation_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("banned_by", sa.BigInteger(), nullable=False),
        sa.Column("banned_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["federation_id"], ["federations.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_fed_bans_fed", "federation_bans", ["federation_id"], unique=False)
    op.create_index("idx_fed_bans_user", "federation_bans", ["telegram_id"], unique=False)
    op.create_index("uq_fed_ban", "federation_bans", ["federation_id", "telegram_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_fed_ban", table_name="federation_bans")
    op.drop_index("idx_fed_bans_user", table_name="federation_bans")
    op.drop_index("idx_fed_bans_fed", table_name="federation_bans")
    op.drop_table("federation_bans")

    op.drop_index("idx_groups_federation", table_name="groups")
    op.drop_constraint("fk_groups_federation_id", "groups", type_="foreignkey")
    op.drop_column("groups", "federation_id")

    op.drop_table("federations")
