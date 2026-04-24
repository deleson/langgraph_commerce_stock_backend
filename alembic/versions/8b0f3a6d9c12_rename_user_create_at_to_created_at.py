"""rename user create_at to created_at

Revision ID: 8b0f3a6d9c12
Revises: 2fa2e0362cfb
Create Date: 2026-04-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8b0f3a6d9c12"
down_revision: Union[str, Sequence[str], None] = "2fa2e0362cfb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("users", "create_at", new_column_name="created_at")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("users", "created_at", new_column_name="create_at")
