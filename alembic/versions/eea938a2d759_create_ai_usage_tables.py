"""create ai usage tables

Revision ID: eea938a2d759
Revises: c0ee12b7d6c8
Create Date: 2026-05-27 04:33:13.143835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eea938a2d759'
down_revision: Union[str, Sequence[str], None] = 'c0ee12b7d6c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_quota_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("daily_call_limit", sa.Integer(), nullable=False),
        sa.Column("monthly_call_limit", sa.Integer(), nullable=False),
        sa.Column("daily_token_limit", sa.Integer(), nullable=False),
        sa.Column("monthly_token_limit", sa.Integer(), nullable=False),
        sa.Column("daily_cost_limit", sa.Numeric(18, 8), nullable=True),
        sa.Column("monthly_cost_limit", sa.Numeric(18, 8), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "daily_call_limit >= 0",
            name=op.f("ck_ai_quota_accounts_ai_quota_account_daily_call_limit_non_negative"),
        ),
        sa.CheckConstraint(
            "monthly_call_limit >= 0",
            name=op.f("ck_ai_quota_accounts_ai_quota_account_monthly_call_limit_non_negative"),
        ),
        sa.CheckConstraint(
            "daily_token_limit >= 0",
            name=op.f("ck_ai_quota_accounts_ai_quota_account_daily_token_limit_non_negative"),
        ),
        sa.CheckConstraint(
            "monthly_token_limit >= 0",
            name=op.f("ck_ai_quota_accounts_ai_quota_account_monthly_token_limit_non_negative"),
        ),
        sa.CheckConstraint(
            "daily_cost_limit IS NULL OR daily_cost_limit >= 0",
            name=op.f("ck_ai_quota_accounts_ai_quota_account_daily_cost_limit_non_negative"),
        ),
        sa.CheckConstraint(
            "monthly_cost_limit IS NULL OR monthly_cost_limit >= 0",
            name=op.f("ck_ai_quota_accounts_ai_quota_account_monthly_cost_limit_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_quota_accounts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_quota_accounts")),
        sa.UniqueConstraint("user_id", name=op.f("uq_ai_quota_accounts_user_id")),
    )
    op.create_index(
        op.f("ix_ai_quota_accounts_user_id"),
        "ai_quota_accounts",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("feature", sa.String(length=60), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("token_source", sa.String(length=30), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("request_id", sa.String(length=120), nullable=True),
        sa.Column("analysis_thread_id", sa.String(length=120), nullable=True),
        sa.Column("trace_id", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "feature IN ('stock_analysis','react_reason','react_final_answer','candidate_ai_explanation')",
            name=op.f("ck_ai_usage_logs_ai_usage_log_feature_valid"),
        ),
        sa.CheckConstraint(
            "provider IN ('deepseek')",
            name=op.f("ck_ai_usage_logs_ai_usage_log_provider_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('success','failed','blocked')",
            name=op.f("ck_ai_usage_logs_ai_usage_log_status_valid"),
        ),
        sa.CheckConstraint(
            "token_source IN ('provider_usage','estimated','mixed','none')",
            name=op.f("ck_ai_usage_logs_ai_usage_log_token_source_valid"),
        ),
        sa.CheckConstraint(
            "prompt_tokens >= 0",
            name=op.f("ck_ai_usage_logs_ai_usage_log_prompt_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "completion_tokens >= 0",
            name=op.f("ck_ai_usage_logs_ai_usage_log_completion_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "total_tokens >= 0",
            name=op.f("ck_ai_usage_logs_ai_usage_log_total_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "estimated_cost >= 0",
            name=op.f("ck_ai_usage_logs_ai_usage_log_estimated_cost_non_negative"),
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name=op.f("ck_ai_usage_logs_ai_usage_log_duration_ms_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_usage_logs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_logs")),
    )
    op.create_index(op.f("ix_ai_usage_logs_user_id"), "ai_usage_logs", ["user_id"])
    op.create_index(op.f("ix_ai_usage_logs_feature"), "ai_usage_logs", ["feature"])
    op.create_index(op.f("ix_ai_usage_logs_status"), "ai_usage_logs", ["status"])
    op.create_index(op.f("ix_ai_usage_logs_request_id"), "ai_usage_logs", ["request_id"])
    op.create_index(op.f("ix_ai_usage_logs_analysis_thread_id"), "ai_usage_logs", ["analysis_thread_id"])
    op.create_index(op.f("ix_ai_usage_logs_trace_id"), "ai_usage_logs", ["trace_id"])
    op.create_index("ix_ai_usage_logs_user_created_at", "ai_usage_logs", ["user_id", "created_at"])
    op.create_index("ix_ai_usage_logs_user_feature_created_at", "ai_usage_logs", ["user_id", "feature", "created_at"])
    op.create_index("ix_ai_usage_logs_user_status_created_at", "ai_usage_logs", ["user_id", "status", "created_at"])

    op.create_table(
        "ai_usage_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("period_type", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("call_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("blocked_count", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "period_type IN ('day','month')",
            name=op.f("ck_ai_usage_summaries_ai_usage_summary_period_type_valid"),
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name=op.f("ck_ai_usage_summaries_ai_usage_summary_period_range_valid"),
        ),
        sa.CheckConstraint(
            "call_count >= 0",
            name=op.f("ck_ai_usage_summaries_ai_usage_summary_call_count_non_negative"),
        ),
        sa.CheckConstraint(
            "success_count >= 0",
            name=op.f("ck_ai_usage_summaries_ai_usage_summary_success_count_non_negative"),
        ),
        sa.CheckConstraint(
            "failed_count >= 0",
            name=op.f("ck_ai_usage_summaries_ai_usage_summary_failed_count_non_negative"),
        ),
        sa.CheckConstraint(
            "blocked_count >= 0",
            name=op.f("ck_ai_usage_summaries_ai_usage_summary_blocked_count_non_negative"),
        ),
        sa.CheckConstraint(
            "prompt_tokens >= 0",
            name=op.f("ck_ai_usage_summaries_ai_usage_summary_prompt_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "completion_tokens >= 0",
            name=op.f("ck_ai_usage_summaries_ai_usage_summary_completion_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "total_tokens >= 0",
            name=op.f("ck_ai_usage_summaries_ai_usage_summary_total_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "estimated_cost >= 0",
            name=op.f("ck_ai_usage_summaries_ai_usage_summary_estimated_cost_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_usage_summaries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_summaries")),
        sa.UniqueConstraint(
            "user_id",
            "period_type",
            "period_start",
            name="uq_ai_usage_summaries_user_period",
        ),
    )
    op.create_index(op.f("ix_ai_usage_summaries_user_id"), "ai_usage_summaries", ["user_id"])
    op.create_index(op.f("ix_ai_usage_summaries_period_type"), "ai_usage_summaries", ["period_type"])
    op.create_index(op.f("ix_ai_usage_summaries_period_start"), "ai_usage_summaries", ["period_start"])
    op.create_index("ix_ai_usage_summaries_user_period", "ai_usage_summaries", ["user_id", "period_type", "period_start"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_summaries_user_period", table_name="ai_usage_summaries")
    op.drop_index(op.f("ix_ai_usage_summaries_period_start"), table_name="ai_usage_summaries")
    op.drop_index(op.f("ix_ai_usage_summaries_period_type"), table_name="ai_usage_summaries")
    op.drop_index(op.f("ix_ai_usage_summaries_user_id"), table_name="ai_usage_summaries")
    op.drop_table("ai_usage_summaries")

    op.drop_index("ix_ai_usage_logs_user_status_created_at", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_user_feature_created_at", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_user_created_at", table_name="ai_usage_logs")
    op.drop_index(op.f("ix_ai_usage_logs_trace_id"), table_name="ai_usage_logs")
    op.drop_index(op.f("ix_ai_usage_logs_analysis_thread_id"), table_name="ai_usage_logs")
    op.drop_index(op.f("ix_ai_usage_logs_request_id"), table_name="ai_usage_logs")
    op.drop_index(op.f("ix_ai_usage_logs_status"), table_name="ai_usage_logs")
    op.drop_index(op.f("ix_ai_usage_logs_feature"), table_name="ai_usage_logs")
    op.drop_index(op.f("ix_ai_usage_logs_user_id"), table_name="ai_usage_logs")
    op.drop_table("ai_usage_logs")

    op.drop_index(op.f("ix_ai_quota_accounts_user_id"), table_name="ai_quota_accounts")
    op.drop_table("ai_quota_accounts")
