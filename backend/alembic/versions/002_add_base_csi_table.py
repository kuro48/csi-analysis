"""Add base_csi table for reference CSI patterns

Revision ID: 002
Revises: 001
Create Date: 2025-12-11 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """ベースCSIテーブルの作成"""
    op.create_table(
        'base_csi',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False, comment='ベースCSIの名前'),
        sa.Column('description', sa.Text, nullable=True, comment='説明'),
        sa.Column('fft_dataframe', JSON, nullable=False, comment='FFT DataFrame（周波数ビン × サブキャリア）'),
        sa.Column('breathing_frequency_hz', sa.Float, nullable=True, comment='呼吸周波数（Hz）'),
        sa.Column('confidence_score', sa.Float, nullable=True, comment='信頼度スコア（0.0-1.0）'),
        sa.Column('best_subcarrier_indices', JSON, nullable=True, comment='最適サブキャリアインデックス[4]'),
        sa.Column('reference_vector', JSON, nullable=False, comment='4次元参照ベクトル（ZKP用）'),
        sa.Column('source_pcap_path', sa.String(500), nullable=True, comment='元のPCAPファイルパス'),
        sa.Column('source_pcap_size', sa.Integer, nullable=True, comment='元のPCAPファイルサイズ（バイト）'),
        sa.Column('expires_at', sa.DateTime, nullable=True, comment='有効期限（Noneの場合は無期限）'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False)
    )

    # インデックスの作成
    op.create_index('ix_base_csi_user_id', 'base_csi', ['user_id'], unique=False)
    op.create_index('ix_base_csi_expires_at', 'base_csi', ['expires_at'], unique=False)
    op.create_index('ix_base_csi_created_at', 'base_csi', ['created_at'], unique=False)


def downgrade() -> None:
    """ベースCSIテーブルの削除"""
    # インデックス削除
    op.drop_index('ix_base_csi_created_at', table_name='base_csi')
    op.drop_index('ix_base_csi_expires_at', table_name='base_csi')
    op.drop_index('ix_base_csi_user_id', table_name='base_csi')

    # テーブル削除
    op.drop_table('base_csi')
