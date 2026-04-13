"""Add music_dataframe to base_csi

Revision ID: 007
Revises: 006
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "base_csi",
        sa.Column(
            "music_dataframe",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="MUSIC DataFrame（周波数ビン × サブキャリア）",
        ),
    )


def downgrade() -> None:
    op.drop_column("base_csi", "music_dataframe")
