"""Add device_id to csi_data

Revision ID: 004
Revises: 003
Create Date: 2026-01-21 06:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """device_idカラム追加"""
    op.add_column("csi_data", sa.Column("device_id", sa.String(length=255), nullable=True))
    op.create_index("ix_csi_data_device_id", "csi_data", ["device_id"], unique=False)


def downgrade() -> None:
    """device_idカラム削除"""
    op.drop_index("ix_csi_data_device_id", table_name="csi_data")
    op.drop_column("csi_data", "device_id")
