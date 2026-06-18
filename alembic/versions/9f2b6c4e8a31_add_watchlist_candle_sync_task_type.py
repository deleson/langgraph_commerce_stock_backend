"""add watchlist candle sync task type

Revision ID: 9f2b6c4e8a31
Revises: f3d9a7b2c641
Create Date: 2026-06-19 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "9f2b6c4e8a31"
down_revision: str | None = "f3d9a7b2c641"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_TASK_TYPES = (
    "'market_data_sync',"
    "'stock_analysis_async',"
    "'candidate_scoring_async',"
    "'candidate_ai_explanation_async',"
    "'user_profile_refresh',"
    "'user_memory_embedding_rebuild',"
    "'daily_report',"
    "'alert_scan',"
    "'paper_trading_tick'"
)

NEW_TASK_TYPES = (
    "'market_data_sync',"
    "'watchlist_candle_sync',"
    "'stock_analysis_async',"
    "'candidate_scoring_async',"
    "'candidate_ai_explanation_async',"
    "'user_profile_refresh',"
    "'user_memory_embedding_rebuild',"
    "'daily_report',"
    "'alert_scan',"
    "'paper_trading_tick'"
)


def upgrade() -> None:
    op.drop_constraint(
        "background_task_type_valid",
        "background_tasks",
        type_="check",
    )
    op.create_check_constraint(
        "background_task_type_valid",
        "background_tasks",
        f"task_type IN ({NEW_TASK_TYPES})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "background_task_type_valid",
        "background_tasks",
        type_="check",
    )
    op.create_check_constraint(
        "background_task_type_valid",
        "background_tasks",
        f"task_type IN ({OLD_TASK_TYPES})",
    )