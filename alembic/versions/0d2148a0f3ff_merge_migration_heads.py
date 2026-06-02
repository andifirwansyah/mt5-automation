"""merge migration heads

Revision ID: 0d2148a0f3ff
Revises: 0d9f9c0b7d22, 20260531_0003
Create Date: 2026-06-02 20:01:59.014570
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0d2148a0f3ff'
down_revision = ('0d9f9c0b7d22', '20260531_0003')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
