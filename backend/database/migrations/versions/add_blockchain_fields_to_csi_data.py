"""add blockchain fields to csi_data

Revision ID: bc123456789a
Revises: 07960c54d42d
Create Date: 2025-10-14 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'bc123456789a'
down_revision = '07960c54d42d'
branch_labels = None
depends_on = None


def upgrade():
    """ブロックチェーン関連フィールドをcsi_dataテーブルに追加"""

    # blockchain_tx_hash フィールドを追加
    op.add_column('csi_data',
        sa.Column('blockchain_tx_hash', sa.String(66), nullable=True,
                  comment='ブロックチェーントランザクションハッシュ')
    )

    # blockchain_status フィールドを追加
    op.add_column('csi_data',
        sa.Column('blockchain_status', sa.String(20),
                  server_default='pending', nullable=False,
                  comment='ブロックチェーン記録状態: pending, confirmed, failed')
    )

    # blockchain_recorded_at フィールドを追加
    op.add_column('csi_data',
        sa.Column('blockchain_recorded_at',
                  sa.DateTime(timezone=True), nullable=True,
                  comment='ブロックチェーン記録完了時刻')
    )

    # インデックスを作成
    op.create_index('idx_blockchain_tx_hash', 'csi_data', ['blockchain_tx_hash'])
    op.create_index('idx_blockchain_status', 'csi_data', ['blockchain_status'])


def downgrade():
    """ブロックチェーン関連フィールドを削除"""

    # インデックスを削除
    op.drop_index('idx_blockchain_status', 'csi_data')
    op.drop_index('idx_blockchain_tx_hash', 'csi_data')

    # カラムを削除
    op.drop_column('csi_data', 'blockchain_recorded_at')
    op.drop_column('csi_data', 'blockchain_status')
    op.drop_column('csi_data', 'blockchain_tx_hash')
