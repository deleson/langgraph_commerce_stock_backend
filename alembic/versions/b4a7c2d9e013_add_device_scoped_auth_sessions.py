"""add device scoped auth sessions

Revision ID: b4a7c2d9e013
Revises: 9f2b6c4e8a31
Create Date: 2026-06-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b4a7c2d9e013"
down_revision: str | None = "9f2b6c4e8a31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_sessions", sa.Column("device_id", sa.Integer(), nullable=True))
    op.add_column(
        "user_sessions",
        sa.Column(
            "device_platform",
            sa.String(length=20),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column(
        "user_sessions",
        sa.Column(
            "device_category",
            sa.String(length=20),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column(
        "user_sessions",
        sa.Column("device_fingerprint_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("app_version", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("access_token_jti", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("revoked_reason", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("replaced_by_session_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_foreign_key(
        "fk_user_sessions_device_id_devices",
        "user_sessions",
        "devices",
        ["device_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_user_sessions_replaced_by_session_id_user_sessions",
        "user_sessions",
        "user_sessions",
        ["replaced_by_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "user_session_device_platform_valid",
        "user_sessions",
        "device_platform IN ('ios','android','web','unknown')",
    )
    op.create_check_constraint(
        "user_session_device_category_valid",
        "user_sessions",
        "device_category IN ('mobile','web','unknown')",
    )
    op.create_check_constraint(
        "user_session_revoked_reason_valid",
        "user_sessions",
        "revoked_reason IS NULL OR revoked_reason IN ("
        "'logout','refresh_rotated','replaced_by_same_category_login',"
        "'admin_revoked','expired'"
        ")",
    )
    op.create_index(
        "ix_user_sessions_user_category_revoked",
        "user_sessions",
        ["user_id", "device_category", "is_revoked"],
        unique=False,
    )
    op.create_index(
        "ix_user_sessions_access_token_jti",
        "user_sessions",
        ["access_token_jti"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_sessions_device_id"),
        "user_sessions",
        ["device_id"],
        unique=False,
    )

    op.alter_column("user_sessions", "device_platform", server_default=None)
    op.alter_column("user_sessions", "device_category", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_sessions_device_id"), table_name="user_sessions")
    op.drop_index("ix_user_sessions_access_token_jti", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_category_revoked", table_name="user_sessions")
    op.drop_constraint("user_session_revoked_reason_valid", "user_sessions", type_="check")
    op.drop_constraint("user_session_device_category_valid", "user_sessions", type_="check")
    op.drop_constraint("user_session_device_platform_valid", "user_sessions", type_="check")
    op.drop_constraint(
        "fk_user_sessions_replaced_by_session_id_user_sessions",
        "user_sessions",
        type_="foreignkey",
    )
    op.drop_constraint("fk_user_sessions_device_id_devices", "user_sessions", type_="foreignkey")
    op.drop_column("user_sessions", "last_seen_at")
    op.drop_column("user_sessions", "replaced_by_session_id")
    op.drop_column("user_sessions", "revoked_reason")
    op.drop_column("user_sessions", "revoked_at")
    op.drop_column("user_sessions", "access_token_jti")
    op.drop_column("user_sessions", "app_version")
    op.drop_column("user_sessions", "device_fingerprint_hash")
    op.drop_column("user_sessions", "device_category")
    op.drop_column("user_sessions", "device_platform")
    op.drop_column("user_sessions", "device_id")