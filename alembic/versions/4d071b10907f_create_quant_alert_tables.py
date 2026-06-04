from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d071b10907f"
down_revision: Union[str, Sequence[str], None] = "0acd45894847"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quant_alert_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("rule_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("trigger_direction", sa.String(length=20), nullable=True),
        sa.Column("threshold_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled_notification", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rule_config", sa.JSON(), nullable=False),
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
            "rule_type IN ("
            "'strategy_signal',"
            "'strong_strategy_signal',"
            "'strategy_score_threshold',"
            "'price_change',"
            "'volume_spike',"
            "'data_quality'"
            ")",
            name=op.f("ck_quant_alert_rules_quant_alert_rule_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive')",
            name=op.f("ck_quant_alert_rules_quant_alert_rule_status_valid"),
        ),
        sa.CheckConstraint(
            "severity IN ('info','warning','critical')",
            name=op.f("ck_quant_alert_rules_quant_alert_rule_severity_valid"),
        ),
        sa.CheckConstraint(
            "trigger_direction IS NULL OR trigger_direction IN ('above','below','equal','changed')",
            name=op.f("ck_quant_alert_rules_quant_alert_rule_trigger_direction_valid"),
        ),
        sa.CheckConstraint(
            "market IS NULL OR market IN ('US','CN','HK')",
            name=op.f("ck_quant_alert_rules_quant_alert_rule_market_valid"),
        ),
        sa.CheckConstraint(
            "cooldown_minutes >= 0",
            name=op.f("ck_quant_alert_rules_quant_alert_rule_cooldown_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_quant_alert_rules_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quant_alert_rules")),
        sa.UniqueConstraint(
            "user_id",
            "rule_type",
            "market",
            "symbol",
            name=op.f("uq_quant_alert_rules_user_type_market_symbol"),
        ),
    )

    op.create_index(
        op.f("ix_quant_alert_rules_user_id"),
        "quant_alert_rules",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_rules_rule_type"),
        "quant_alert_rules",
        ["rule_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_rules_status"),
        "quant_alert_rules",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_rules_market"),
        "quant_alert_rules",
        ["market"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_rules_symbol"),
        "quant_alert_rules",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_quant_alert_rules_user_status",
        "quant_alert_rules",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_quant_alert_rules_user_type",
        "quant_alert_rules",
        ["user_id", "rule_type"],
        unique=False,
    )
    op.create_index(
        "ix_quant_alert_rules_user_symbol",
        "quant_alert_rules",
        ["user_id", "market", "symbol"],
        unique=False,
    )

    op.create_table(
        "quant_alert_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("rule_type", sa.String(length=60), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dedup_key", sa.String(length=255), nullable=False),
        sa.Column("trigger_snapshot", sa.JSON(), nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=True),
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
            "rule_type IN ("
            "'strategy_signal',"
            "'strong_strategy_signal',"
            "'strategy_score_threshold',"
            "'price_change',"
            "'volume_spike',"
            "'data_quality'"
            ")",
            name=op.f("ck_quant_alert_events_quant_alert_event_rule_type_valid"),
        ),
        sa.CheckConstraint(
            "severity IN ('info','warning','critical')",
            name=op.f("ck_quant_alert_events_quant_alert_event_severity_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('triggered','acknowledged','ignored')",
            name=op.f("ck_quant_alert_events_quant_alert_event_status_valid"),
        ),
        sa.CheckConstraint(
            "market IN ('US','CN','HK')",
            name=op.f("ck_quant_alert_events_quant_alert_event_market_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_quant_alert_events_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["quant_alert_rules.id"],
            ondelete="SET NULL",
            name=op.f("fk_quant_alert_events_rule_id_quant_alert_rules"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quant_alert_events")),
        sa.UniqueConstraint(
            "user_id",
            "dedup_key",
            name=op.f("uq_quant_alert_events_user_dedup_key"),
        ),
    )

    op.create_index(
        op.f("ix_quant_alert_events_user_id"),
        "quant_alert_events",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_events_rule_id"),
        "quant_alert_events",
        ["rule_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_events_rule_type"),
        "quant_alert_events",
        ["rule_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_events_symbol"),
        "quant_alert_events",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_events_market"),
        "quant_alert_events",
        ["market"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_events_status"),
        "quant_alert_events",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_events_event_date"),
        "quant_alert_events",
        ["event_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_events_triggered_at"),
        "quant_alert_events",
        ["triggered_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quant_alert_events_notification_id"),
        "quant_alert_events",
        ["notification_id"],
        unique=False,
    )
    op.create_index(
        "ix_quant_alert_events_user_event_date",
        "quant_alert_events",
        ["user_id", "event_date"],
        unique=False,
    )
    op.create_index(
        "ix_quant_alert_events_user_status",
        "quant_alert_events",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_quant_alert_events_user_symbol",
        "quant_alert_events",
        ["user_id", "market", "symbol"],
        unique=False,
    )
    op.create_index(
        "ix_quant_alert_events_user_rule_type",
        "quant_alert_events",
        ["user_id", "rule_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_quant_alert_events_user_rule_type", table_name="quant_alert_events")
    op.drop_index("ix_quant_alert_events_user_symbol", table_name="quant_alert_events")
    op.drop_index("ix_quant_alert_events_user_status", table_name="quant_alert_events")
    op.drop_index("ix_quant_alert_events_user_event_date", table_name="quant_alert_events")
    op.drop_index(op.f("ix_quant_alert_events_notification_id"), table_name="quant_alert_events")
    op.drop_index(op.f("ix_quant_alert_events_triggered_at"), table_name="quant_alert_events")
    op.drop_index(op.f("ix_quant_alert_events_event_date"), table_name="quant_alert_events")
    op.drop_index(op.f("ix_quant_alert_events_status"), table_name="quant_alert_events")
    op.drop_index(op.f("ix_quant_alert_events_market"), table_name="quant_alert_events")
    op.drop_index(op.f("ix_quant_alert_events_symbol"), table_name="quant_alert_events")
    op.drop_index(op.f("ix_quant_alert_events_rule_type"), table_name="quant_alert_events")
    op.drop_index(op.f("ix_quant_alert_events_rule_id"), table_name="quant_alert_events")
    op.drop_index(op.f("ix_quant_alert_events_user_id"), table_name="quant_alert_events")
    op.drop_table("quant_alert_events")

    op.drop_index("ix_quant_alert_rules_user_symbol", table_name="quant_alert_rules")
    op.drop_index("ix_quant_alert_rules_user_type", table_name="quant_alert_rules")
    op.drop_index("ix_quant_alert_rules_user_status", table_name="quant_alert_rules")
    op.drop_index(op.f("ix_quant_alert_rules_symbol"), table_name="quant_alert_rules")
    op.drop_index(op.f("ix_quant_alert_rules_market"), table_name="quant_alert_rules")
    op.drop_index(op.f("ix_quant_alert_rules_status"), table_name="quant_alert_rules")
    op.drop_index(op.f("ix_quant_alert_rules_rule_type"), table_name="quant_alert_rules")
    op.drop_index(op.f("ix_quant_alert_rules_user_id"), table_name="quant_alert_rules")
    op.drop_table("quant_alert_rules")