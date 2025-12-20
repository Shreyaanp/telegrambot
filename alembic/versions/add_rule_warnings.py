"""add rule warnings and escalation

Revision ID: add_rule_warnings
Revises: add_welcome_destination
Create Date: 2024-12-20 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_rule_warnings'
down_revision = 'add_welcome_destination'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add warn_threshold and warn_escalation_action to rules table
    op.add_column('rules', sa.Column('warn_threshold', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('rules', sa.Column('warn_escalation_action', sa.String(), nullable=False, server_default='kick'))
    
    # Create rule_warnings table
    op.create_table(
        'rule_warnings',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('rule_id', sa.BigInteger(), nullable=False),
        sa.Column('group_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('warned_at', sa.DateTime(), nullable=True),
        sa.Column('message_text', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['rule_id'], ['rules.id'], ),
        sa.ForeignKeyConstraint(['group_id'], ['groups.group_id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_rule_warnings_lookup', 'rule_warnings', ['rule_id', 'telegram_id', 'warned_at'])
    op.create_index('idx_rule_warnings_group_user', 'rule_warnings', ['group_id', 'telegram_id'])


def downgrade() -> None:
    # Drop rule_warnings table
    op.drop_index('idx_rule_warnings_group_user', table_name='rule_warnings')
    op.drop_index('idx_rule_warnings_lookup', table_name='rule_warnings')
    op.drop_table('rule_warnings')
    
    # Remove columns from rules table
    op.drop_column('rules', 'warn_escalation_action')
    op.drop_column('rules', 'warn_threshold')
