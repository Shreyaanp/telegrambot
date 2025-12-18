"""add dm subscribers

Revision ID: 9253c91911b1
Revises: 1604c0e0ca30
Create Date: 2025-12-18 16:29:15.728492

"""

from alembic import op
import sqlalchemy as sa



revision = '9253c91911b1'
down_revision = '1604c0e0ca30'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'dm_subscribers',
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('first_name', sa.String(), nullable=True),
        sa.Column('last_name', sa.String(), nullable=True),
        sa.Column('opted_out', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('deliverable', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('fail_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.Column('last_ok_at', sa.DateTime(), nullable=True),
        sa.Column('last_fail_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('telegram_id'),
    )
    op.create_index('idx_dm_subscribers_delivery', 'dm_subscribers', ['deliverable', 'opted_out'], unique=False)
    op.create_index('idx_dm_subscribers_last_seen', 'dm_subscribers', ['last_seen_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_dm_subscribers_last_seen', table_name='dm_subscribers')
    op.drop_index('idx_dm_subscribers_delivery', table_name='dm_subscribers')
    op.drop_table('dm_subscribers')
