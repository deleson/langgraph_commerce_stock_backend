"""add market symbol source sync

Revision ID: f3d9a7b2c641
Revises: a558f95a7ef5
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f3d9a7b2c641"
down_revision: str | None = "a558f95a7ef5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "market_symbols",
        sa.Column("list_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "market_symbols",
        sa.Column("data_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "market_symbols",
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "market_symbols",
        sa.Column("sync_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "market_symbols",
        sa.Column("last_sync_error", sa.String(length=500), nullable=True),
    )

    op.create_table(
        "market_symbol_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_symbol", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("exchange", sa.String(length=30), nullable=True),
        sa.Column("list_status", sa.String(length=30), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("raw_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_hash", sa.String(length=64), nullable=False),
        sa.Column("sync_status", sa.String(length=30), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sync_error", sa.String(length=500), nullable=True),
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
            "market IN ('US','CN','HK')",
            name=op.f("ck_market_symbol_sources_market_symbol_sources_market_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_symbol_sources")),
        sa.UniqueConstraint(
            "provider",
            "market",
            "symbol",
            name="uq_market_symbol_sources_provider_market_symbol",
        ),
    )
    op.create_index(
        op.f("ix_market_symbol_sources_market"),
        "market_symbol_sources",
        ["market"],
        unique=False,
    )
    op.create_index(
        op.f("ix_market_symbol_sources_provider"),
        "market_symbol_sources",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_market_symbol_sources_symbol"),
        "market_symbol_sources",
        ["symbol"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_market_symbol_sources_symbol"), table_name="market_symbol_sources")
    op.drop_index(op.f("ix_market_symbol_sources_provider"), table_name="market_symbol_sources")
    op.drop_index(op.f("ix_market_symbol_sources_market"), table_name="market_symbol_sources")
    op.drop_table("market_symbol_sources")

    op.drop_column("market_symbols", "last_sync_error")
    op.drop_column("market_symbols", "sync_status")
    op.drop_column("market_symbols", "last_synced_at")
    op.drop_column("market_symbols", "data_hash")
    op.drop_column("market_symbols", "list_status")
