"""Remove ipfs_hash from csi_data

Revision ID: 003
Revises: 002
Create Date: 2025-01-21 12:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """IPFS関連カラムの削除"""
    try:
        op.drop_index("ix_csi_data_ipfs_hash", table_name="csi_data")
    except Exception:
        pass

    try:
        op.drop_column("csi_data", "ipfs_hash")
    except Exception:
        pass


def downgrade() -> None:
    """IPFS関連カラムの復元"""
    op.add_column("csi_data", sa.Column("ipfs_hash", sa.String(length=255), nullable=True))
    op.create_index("ix_csi_data_ipfs_hash", "csi_data", ["ipfs_hash"], unique=False)
