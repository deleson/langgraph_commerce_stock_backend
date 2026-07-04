"""add paper trading account universe

Revision ID: c8f4a2d7e901
Revises: b4a7c2d9e013
Create Date: 2026-07-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c8f4a2d7e901"
down_revision: str | None = "b4a7c2d9e013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_trading_accounts",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "background_tasks",
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
    )
    op.create_index(
        "ux_background_tasks_idempotency_key",
        "background_tasks",
        ["idempotency_key"],
        unique=True,
    )
    op.create_table(
        "paper_trading_account_symbols",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("source_watchlist_item_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "market IN ('US','CN','HK')",
            name="ck_paper_trading_account_symbols_market_valid",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["paper_trading_accounts.id"],
            name="fk_pt_account_symbols_account_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_paper_trading_account_symbols"),
        sa.UniqueConstraint(
            "account_id",
            "market",
            "symbol",
            name="uq_paper_trading_account_symbols_account_market_symbol",
        ),
    )
    op.create_index(
        "ix_paper_trading_account_symbols_account_id",
        "paper_trading_account_symbols",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_paper_trading_account_symbols_account_order",
        "paper_trading_account_symbols",
        ["account_id", "id"],
        unique=False,
    )

    # 新增 no_universe 业务状态；旧约束不包含该值，会导致空组合运行记录落库失败。
    op.drop_constraint(
        op.f("ck_paper_trading_runs_paper_trading_run_unavailable_rea_bbc9"),
        "paper_trading_runs",
        type_="check",
    )
    op.create_check_constraint(
        "paper_trading_run_unavailable_reason_valid",
        "paper_trading_runs",
        "unavailable_reason IS NULL OR unavailable_reason IN ("
        "'no_account','no_watchlist','no_universe','no_data',"
        "'data_error','market_closed','tick_failed'"
        ")",
    )

    # 兼容已有生产账户：迁移时把每个用户当前最多 50 只自选股冻结为一次快照。
    # 后续用户再增删自选股不会改变这些记录。
    op.execute(
        sa.text(
            """
            INSERT INTO paper_trading_account_symbols
                (account_id, symbol, market, name, source_watchlist_item_id, created_at)
            SELECT account.id, selected.symbol, selected.market, selected.name, selected.id, now()
            FROM paper_trading_accounts AS account
            JOIN LATERAL (
                SELECT item.id, item.symbol, item.market, item.name
                FROM watchlist_items AS item
                WHERE item.user_id = account.user_id
                ORDER BY item.created_at ASC, item.id ASC
                LIMIT 50
            ) AS selected ON TRUE
            ON CONFLICT (account_id, market, symbol) DO NOTHING
            """
        )
    )

    # 极端情况下旧账户持仓已不在自选股中，也必须继续进入固定组合以便后续卖出。
    op.execute(
        sa.text(
            """
            INSERT INTO paper_trading_account_symbols
                (account_id, symbol, market, name, source_watchlist_item_id, created_at)
            SELECT position.account_id, position.symbol, position.market, NULL, NULL, now()
            FROM paper_trading_positions AS position
            WHERE position.quantity > 0
            ON CONFLICT (account_id, market, symbol) DO NOTHING
            """
        )
    )

    # 旧账户可能把扫描上限调得比迁移后的固定股票池更小；迁移时抬高到完整组合数。
    op.execute(
        sa.text(
            """
            UPDATE paper_trading_account_configs AS config
            SET max_symbols_per_tick = universe.symbol_count,
                updated_at = now()
            FROM (
                SELECT account_id, COUNT(*) AS symbol_count
                FROM paper_trading_account_symbols
                GROUP BY account_id
            ) AS universe
            WHERE config.account_id = universe.account_id
              AND config.max_symbols_per_tick < universe.symbol_count
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE paper_trading_accounts
            SET closed_at = updated_at
            WHERE status = 'closed' AND closed_at IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_paper_trading_runs_paper_trading_run_unavailable_rea_bbc9"),
        "paper_trading_runs",
        type_="check",
    )
    op.create_check_constraint(
        "paper_trading_run_unavailable_reason_valid",
        "paper_trading_runs",
        "unavailable_reason IS NULL OR unavailable_reason IN ("
        "'no_account','no_watchlist','no_data','data_error',"
        "'market_closed','tick_failed'"
        ")",
    )
    op.drop_index(
        "ix_paper_trading_account_symbols_account_order",
        table_name="paper_trading_account_symbols",
    )
    op.drop_index(
        "ix_paper_trading_account_symbols_account_id",
        table_name="paper_trading_account_symbols",
    )
    op.drop_table("paper_trading_account_symbols")
    op.drop_index(
        "ux_background_tasks_idempotency_key",
        table_name="background_tasks",
    )
    op.drop_column("background_tasks", "idempotency_key")
    op.drop_column("paper_trading_accounts", "closed_at")
