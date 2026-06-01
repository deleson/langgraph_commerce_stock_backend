from typing import Sequence, Union

from alembic import op


revision: str = "e2b92f1312a5"
down_revision: Union[str, Sequence[str], None] = "00a1244faf73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "background_task_type_valid",
        "background_tasks",
        type_="check",
    )
    op.create_check_constraint(
        "background_task_type_valid",
        "background_tasks",
        "task_type IN ("
        "'market_data_sync',"
        "'stock_analysis_async',"
        "'candidate_scoring_async',"
        "'candidate_ai_explanation_async',"
        "'user_profile_refresh',"
        "'user_memory_embedding_rebuild',"
        "'daily_report',"
        "'alert_scan',"
        "'paper_trading_tick'"
        ")",
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
        "task_type IN ("
        "'market_data_sync',"
        "'stock_analysis_async',"
        "'candidate_scoring_async',"
        "'candidate_ai_explanation_async',"
        "'user_profile_refresh',"
        "'daily_report',"
        "'alert_scan',"
        "'paper_trading_tick'"
        ")",
    )