"""Add ipfs_hash to csi_data and breathing_analyses tables

Revision ID: 001
Revises:
Create Date: 2024-09-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """IPFS連携のためのカラム追加"""
    # csi_dataテーブルにipfs_hashカラムを追加
    op.add_column('csi_data', sa.Column('ipfs_hash', sa.String(length=255), nullable=True))
    op.create_index('ix_csi_data_ipfs_hash', 'csi_data', ['ipfs_hash'], unique=False)

    # breathing_analysesテーブルにもipfs_hashカラムが必要な場合は追加
    # （既に存在している可能性があるため、条件付きで追加）
    try:
        op.add_column('breathing_analyses', sa.Column('ipfs_hash', sa.String(length=255), nullable=True))
        op.create_index('ix_breathing_analyses_ipfs_hash', 'breathing_analyses', ['ipfs_hash'], unique=False)
    except Exception:
        # カラムが既に存在する場合はスキップ
        pass


def downgrade() -> None:
    """IPFS関連カラムの削除"""
    # インデックス削除
    op.drop_index('ix_csi_data_ipfs_hash', table_name='csi_data')
    try:
        op.drop_index('ix_breathing_analyses_ipfs_hash', table_name='breathing_analyses')
    except Exception:
        pass

    # カラム削除
    op.drop_column('csi_data', 'ipfs_hash')
    try:
        op.drop_column('breathing_analyses', 'ipfs_hash')
    except Exception:
        pass