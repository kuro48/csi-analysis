"""Add wavelet_dataframe to base_csi

Revision ID: 005
Revises: 004
Create Date: 2026-04-09 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """base_csi に wavelet_dataframe を追加"""
    op.add_column(
        "base_csi",
        sa.Column(
            "wavelet_dataframe",
            sa.JSON(),
            nullable=True,
            comment="Wavelet DataFrame（周波数ビン × サブキャリア）",
        ),
    )


def downgrade() -> None:
    """base_csi から wavelet_dataframe を削除"""
    op.drop_column("base_csi", "wavelet_dataframe")
