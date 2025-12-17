from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("group_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("group_name", sa.String(), nullable=True),
        sa.Column("verification_enabled", sa.Boolean(), nullable=True),
        sa.Column("verification_timeout", sa.Integer(), nullable=True),
        sa.Column("kick_unverified", sa.Boolean(), nullable=True),
        sa.Column("join_gate_enabled", sa.Boolean(), nullable=True),
        sa.Column("welcome_enabled", sa.Boolean(), nullable=True),
        sa.Column("welcome_message", sa.Text(), nullable=True),
        sa.Column("goodbye_enabled", sa.Boolean(), nullable=True),
        sa.Column("goodbye_message", sa.Text(), nullable=True),
        sa.Column("warn_limit", sa.Integer(), nullable=True),
        sa.Column("antiflood_enabled", sa.Boolean(), nullable=True),
        sa.Column("antiflood_limit", sa.Integer(), nullable=True),
        sa.Column("lock_links", sa.Boolean(), nullable=True),
        sa.Column("lock_media", sa.Boolean(), nullable=True),
        sa.Column("logs_enabled", sa.Boolean(), nullable=True),
        sa.Column("logs_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("logs_thread_id", sa.BigInteger(), nullable=True),
        sa.Column("rules_text", sa.Text(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("group_id"),
    )

    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("mercle_user_id", sa.String(), nullable=False),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("is_banned", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("telegram_id"),
        sa.UniqueConstraint("mercle_user_id"),
    )

    op.create_table(
        "admin_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_admin_logs", "admin_logs", ["group_id", "timestamp"], unique=False)
    op.create_index("idx_target_logs", "admin_logs", ["group_id", "target_id"], unique=False)

    op.create_table(
        "config_link_tokens",
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index("idx_cfg_token_expiry", "config_link_tokens", ["expires_at"], unique=False)
    op.create_index("idx_cfg_token_group_admin", "config_link_tokens", ["group_id", "admin_id"], unique=False)

    op.create_table(
        "dm_panel_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("panel_type", sa.String(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_dm_panel_lookup", "dm_panel_state", ["telegram_id", "panel_type", "group_id"], unique=True)

    op.create_table(
        "filters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("filter_type", sa.String(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_group_filter", "filters", ["group_id", "keyword"], unique=False)

    op.create_table(
        "flood_tracker",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=True),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("last_message", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_flood_tracking", "flood_tracker", ["group_id", "telegram_id"], unique=False)

    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=True),
        sa.Column("is_muted", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.ForeignKeyConstraint(["telegram_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_group_member", "group_members", ["group_id", "telegram_id"], unique=False)

    op.create_table(
        "group_user_state",
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("username_lc", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("last_source", sa.String(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("join_count", sa.Integer(), nullable=True),
        sa.Column("first_verified_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_verification_session_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("group_id", "telegram_id"),
    )
    op.create_index("idx_group_user_username", "group_user_state", ["group_id", "username_lc"], unique=False)

    op.create_table(
        "group_wizard_state",
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("wizard_completed", sa.Boolean(), nullable=True),
        sa.Column("wizard_step", sa.Integer(), nullable=True),
        sa.Column("setup_card_message_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("group_id"),
    )

    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("note_name", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("file_id", sa.String(), nullable=True),
        sa.Column("file_type", sa.String(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_group_note", "notes", ["group_id", "note_name"], unique=True)

    op.create_table(
        "pending_join_verifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("join_request_at", sa.DateTime(), nullable=True),
        sa.Column("user_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("prompt_message_id", sa.BigInteger(), nullable=True),
        sa.Column("dm_message_id", sa.BigInteger(), nullable=True),
        sa.Column("mercle_session_id", sa.String(), nullable=True),
        sa.Column("decided_by", sa.BigInteger(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pv_group_user", "pending_join_verifications", ["group_id", "telegram_id"], unique=False)
    op.create_index("idx_pv_status_expiry", "pending_join_verifications", ["status", "expires_at"], unique=False)
    op.create_index("idx_pv_expires_at", "pending_join_verifications", ["expires_at"], unique=False)
    op.create_index(
        "uq_pv_active",
        "pending_join_verifications",
        ["group_id", "telegram_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status='pending'"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("can_verify", sa.Boolean(), nullable=True),
        sa.Column("can_kick", sa.Boolean(), nullable=True),
        sa.Column("can_ban", sa.Boolean(), nullable=True),
        sa.Column("can_warn", sa.Boolean(), nullable=True),
        sa.Column("can_manage_notes", sa.Boolean(), nullable=True),
        sa.Column("can_manage_filters", sa.Boolean(), nullable=True),
        sa.Column("can_manage_settings", sa.Boolean(), nullable=True),
        sa.Column("can_manage_locks", sa.Boolean(), nullable=True),
        sa.Column("can_manage_roles", sa.Boolean(), nullable=True),
        sa.Column("can_view_status", sa.Boolean(), nullable=True),
        sa.Column("can_view_logs", sa.Boolean(), nullable=True),
        sa.Column("granted_by", sa.BigInteger(), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "verification_sessions",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(), nullable=True),
        sa.Column("group_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("message_ids", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("idx_telegram_status", "verification_sessions", ["telegram_id", "status"], unique=False)

    op.create_table(
        "verification_link_tokens",
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("pending_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["pending_id"], ["pending_join_verifications.id"]),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index("idx_ver_token_expiry", "verification_link_tokens", ["expires_at"], unique=False)
    op.create_index("idx_ver_token_pending", "verification_link_tokens", ["pending_id"], unique=False)
    op.create_index(
        "idx_ver_token_pending_expiry_used",
        "verification_link_tokens",
        ["pending_id", "expires_at", "used_at"],
        unique=False,
    )

    op.create_table(
        "warnings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("warned_by", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("warned_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_group_user_warnings", "warnings", ["group_id", "telegram_id"], unique=False)

    op.create_table(
        "whitelist",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("added_by", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_group_user_whitelist", "whitelist", ["group_id", "telegram_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_group_user_whitelist", table_name="whitelist")
    op.drop_table("whitelist")

    op.drop_index("idx_group_user_warnings", table_name="warnings")
    op.drop_table("warnings")

    op.drop_index("idx_ver_token_pending_expiry_used", table_name="verification_link_tokens")
    op.drop_index("idx_ver_token_pending", table_name="verification_link_tokens")
    op.drop_index("idx_ver_token_expiry", table_name="verification_link_tokens")
    op.drop_table("verification_link_tokens")

    op.drop_index("idx_telegram_status", table_name="verification_sessions")
    op.drop_table("verification_sessions")

    op.drop_table("permissions")

    op.drop_index("uq_pv_active", table_name="pending_join_verifications")
    op.drop_index("idx_pv_expires_at", table_name="pending_join_verifications")
    op.drop_index("idx_pv_status_expiry", table_name="pending_join_verifications")
    op.drop_index("idx_pv_group_user", table_name="pending_join_verifications")
    op.drop_table("pending_join_verifications")

    op.drop_index("idx_group_note", table_name="notes")
    op.drop_table("notes")

    op.drop_table("group_wizard_state")

    op.drop_index("idx_group_user_username", table_name="group_user_state")
    op.drop_table("group_user_state")

    op.drop_index("idx_group_member", table_name="group_members")
    op.drop_table("group_members")

    op.drop_index("idx_flood_tracking", table_name="flood_tracker")
    op.drop_table("flood_tracker")

    op.drop_index("idx_group_filter", table_name="filters")
    op.drop_table("filters")

    op.drop_index("idx_dm_panel_lookup", table_name="dm_panel_state")
    op.drop_table("dm_panel_state")

    op.drop_index("idx_cfg_token_group_admin", table_name="config_link_tokens")
    op.drop_index("idx_cfg_token_expiry", table_name="config_link_tokens")
    op.drop_table("config_link_tokens")

    op.drop_index("idx_target_logs", table_name="admin_logs")
    op.drop_index("idx_admin_logs", table_name="admin_logs")
    op.drop_table("admin_logs")

    op.drop_table("users")
    op.drop_table("groups")
