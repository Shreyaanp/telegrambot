"""enhance_ticket_system_with_messages

Revision ID: 7d69a0041f4c
Revises: e1c9a8b7d6f5
Create Date: 2025-12-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7d69a0041f4c'
down_revision = 'e1c9a8b7d6f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ticket_messages table
    op.create_table(
        'ticket_messages',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('ticket_id', sa.BigInteger(), nullable=False),
        sa.Column('sender_type', sa.String(), nullable=False),
        sa.Column('sender_id', sa.BigInteger(), nullable=True),
        sa.Column('sender_name', sa.String(), nullable=True),
        sa.Column('message_type', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('file_id', sa.String(), nullable=True),
        sa.Column('telegram_message_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ticket_msg_ticket', 'ticket_messages', ['ticket_id', 'created_at'], unique=False)
    op.create_index('idx_ticket_msg_sender', 'ticket_messages', ['sender_id', 'created_at'], unique=False)

    # Add new columns to tickets table
    op.add_column('tickets', sa.Column('priority', sa.String(), nullable=False, server_default='normal'))
    op.add_column('tickets', sa.Column('assigned_to', sa.BigInteger(), nullable=True))
    op.add_column('tickets', sa.Column('category', sa.String(), nullable=True))
    op.add_column('tickets', sa.Column('last_message_at', sa.DateTime(), nullable=True))
    op.add_column('tickets', sa.Column('last_staff_reply_at', sa.DateTime(), nullable=True))
    op.add_column('tickets', sa.Column('last_user_message_at', sa.DateTime(), nullable=True))
    op.add_column('tickets', sa.Column('message_count', sa.Integer(), nullable=False, server_default='1'))

    # Add indexes for new columns
    op.create_index('idx_ticket_priority', 'tickets', ['priority', 'status'], unique=False)
    op.create_index('idx_ticket_assigned', 'tickets', ['assigned_to', 'status'], unique=False)

    # Add new columns to ticket_user_state table
    op.add_column('ticket_user_state', sa.Column('creating_ticket', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('ticket_user_state', sa.Column('last_message_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove columns from ticket_user_state
    op.drop_column('ticket_user_state', 'last_message_at')
    op.drop_column('ticket_user_state', 'creating_ticket')

    # Remove indexes from tickets
    op.drop_index('idx_ticket_assigned', table_name='tickets')
    op.drop_index('idx_ticket_priority', table_name='tickets')

    # Remove columns from tickets
    op.drop_column('tickets', 'message_count')
    op.drop_column('tickets', 'last_user_message_at')
    op.drop_column('tickets', 'last_staff_reply_at')
    op.drop_column('tickets', 'last_message_at')
    op.drop_column('tickets', 'category')
    op.drop_column('tickets', 'assigned_to')
    op.drop_column('tickets', 'priority')

    # Drop ticket_messages table
    op.drop_index('idx_ticket_msg_sender', table_name='ticket_messages')
    op.drop_index('idx_ticket_msg_ticket', table_name='ticket_messages')
    op.drop_table('ticket_messages')
