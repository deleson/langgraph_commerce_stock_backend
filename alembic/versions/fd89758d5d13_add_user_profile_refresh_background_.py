from typing import Sequence, Union

from alembic import op


revision: str = "fd89758d5d13"
down_revision: Union[str, Sequence[str], None] = "840738816a2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_TASK_TYPES = (
    "'market_data_sync',"
    "'stock_analysis_async',"
    "'candidate_scoring_async',"
    "'candidate_ai_explanation_async',"
    "'daily_report',"
    "'alert_scan',"
    "'paper_trading_tick'"
)

NEW_TASK_TYPES = (
    "'market_data_sync',"
    "'stock_analysis_async',"
    "'candidate_scoring_async',"
    "'candidate_ai_explanation_async',"
    "'user_profile_refresh',"
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