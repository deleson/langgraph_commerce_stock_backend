from typing import Sequence, Union

from alembic import op


revision: str = "0acd45894847"
down_revision: Union[str, Sequence[str], None] = "5d065d4b5f92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_ai_usage_logs_ai_usage_log_feature_valid"),
        "ai_usage_logs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ai_usage_logs_ai_usage_log_feature_valid"),
        "ai_usage_logs",
        "feature IN ("
        "'stock_analysis',"
        "'react_reason',"
        "'react_final_answer',"
        "'candidate_ai_explanation',"
        "'daily_report'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_ai_usage_logs_ai_usage_log_feature_valid"),
        "ai_usage_logs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ai_usage_logs_ai_usage_log_feature_valid"),
        "ai_usage_logs",
        "feature IN ("
        "'stock_analysis',"
        "'react_reason',"
        "'react_final_answer',"
        "'candidate_ai_explanation'"
        ")",
    )
