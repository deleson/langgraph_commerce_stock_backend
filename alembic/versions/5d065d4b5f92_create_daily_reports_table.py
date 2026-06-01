from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "5d065d4b5f92"
down_revision: Union[str, Sequence[str], None] = "e2b92f1312a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stock_snapshots", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("market_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("technical_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("strategy_signal_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("memory_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ai_used", sa.Boolean(), nullable=False),
        sa.Column("ai_status", sa.String(length=32), nullable=False),
        sa.Column("ai_usage_log_id", sa.Integer(), nullable=True),
        sa.Column("notification_id", sa.Integer(), nullable=True),
        sa.Column("unavailable_reason", sa.String(length=64), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "ai_status IN ('not_used', 'success', 'quota_blocked', 'llm_error', 'parse_error', 'fallback')",
            name="ck_daily_reports_ai_status",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'api', 'background_task', 'scheduler')",
            name="ck_daily_reports_source",
        ),
        sa.CheckConstraint(
            "status IN ('generated', 'fallback', 'failed')",
            name="ck_daily_reports_status",
        ),
        sa.CheckConstraint(
            "unavailable_reason IS NULL OR unavailable_reason IN ('empty_watchlist', 'no_data', 'data_error', 'generation_failed')",
            name="ck_daily_reports_unavailable_reason",
        ),
        sa.ForeignKeyConstraint(
            ["ai_usage_log_id"],
            ["ai_usage_logs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "report_date",
            name="uq_daily_reports_user_id_report_date",
        ),
    )
    op.create_index(
        op.f("ix_daily_reports_id"),
        "daily_reports",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_daily_reports_user_id"),
        "daily_reports",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_daily_reports_report_date"),
        "daily_reports",
        ["report_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_daily_reports_status"),
        "daily_reports",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_daily_reports_source"),
        "daily_reports",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_daily_reports_ai_status"),
        "daily_reports",
        ["ai_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_daily_reports_ai_usage_log_id"),
        "daily_reports",
        ["ai_usage_log_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_daily_reports_notification_id"),
        "daily_reports",
        ["notification_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_daily_reports_unavailable_reason"),
        "daily_reports",
        ["unavailable_reason"],
        unique=False,
    )
    op.create_index(
        "ix_daily_reports_user_id_report_date_desc",
        "daily_reports",
        ["user_id", "report_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_daily_reports_user_id_report_date_desc", table_name="daily_reports")
    op.drop_index(op.f("ix_daily_reports_unavailable_reason"), table_name="daily_reports")
    op.drop_index(op.f("ix_daily_reports_notification_id"), table_name="daily_reports")
    op.drop_index(op.f("ix_daily_reports_ai_usage_log_id"), table_name="daily_reports")
    op.drop_index(op.f("ix_daily_reports_ai_status"), table_name="daily_reports")
    op.drop_index(op.f("ix_daily_reports_source"), table_name="daily_reports")
    op.drop_index(op.f("ix_daily_reports_status"), table_name="daily_reports")
    op.drop_index(op.f("ix_daily_reports_report_date"), table_name="daily_reports")
    op.drop_index(op.f("ix_daily_reports_user_id"), table_name="daily_reports")
    op.drop_index(op.f("ix_daily_reports_id"), table_name="daily_reports")
    op.drop_table("daily_reports")