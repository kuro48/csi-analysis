"""Add subcarrier_medians to base_csi

Revision ID: 008
Revises: 007
Create Date: 2026-06-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "base_csi",
        sa.Column(
            "subcarrier_medians",
            sa.JSON(),
            nullable=True,
            comment="背景差分除去に使用するサブキャリア別メジアン振幅",
        ),
    )


def downgrade() -> None:
    op.drop_column("base_csi", "subcarrier_medians")
