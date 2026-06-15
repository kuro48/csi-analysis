"""Add raw_signal and filtered_signal dataframes to base_csi

Revision ID: 009
Revises: 008
Create Date: 2026-06-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "base_csi",
        sa.Column("raw_signal_dataframe", sa.JSON(), nullable=True),
    )
    op.add_column(
        "base_csi",
        sa.Column("filtered_signal_dataframe", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("base_csi", "filtered_signal_dataframe")
    op.drop_column("base_csi", "raw_signal_dataframe")
