"""
CSIデータモデル
"""

from sqlalchemy import Column, String, Integer, BigInteger, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import BaseModel


class CSIData(BaseModel):
    """CSIデータテーブル"""
    __tablename__ = "csi_data"

    # デバイス関連
    device_id = Column(
        BaseModel.id.type,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # セッション管理
    session_id = Column(String(255), nullable=True, index=True)

    # データ情報
    raw_data = Column(JSONB, nullable=True)
    processed_data = Column(JSONB, nullable=True)

    # ファイル情報
    file_path = Column(String(500), nullable=True)
    file_size = Column(BigInteger, nullable=True, index=True)  # サイズ検索用
    ipfs_hash = Column(String(255), nullable=True, index=True)  # IPFS検索用

    # ステータス
    status = Column(String(50), default="received", nullable=False, index=True)  # ステータス検索用

    # ブロックチェーン関連フィールド
    blockchain_tx_hash = Column(
        String(66),
        nullable=True,
        index=True,
        comment="ブロックチェーントランザクションハッシュ"
    )
    blockchain_status = Column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        comment="ブロックチェーン記録状態: pending, confirmed, failed"
    )
    blockchain_recorded_at = Column(
        BaseModel.created_at.type,
        nullable=True,
        comment="ブロックチェーン記録完了時刻"
    )

    # 複合インデックス - CSIデータ固有のクエリパターン用
    __table_args__ = (
        Index('idx_csi_device_created', 'device_id', 'created_at'),  # デバイス別時系列検索用
        Index('idx_csi_device_status', 'device_id', 'status'),  # デバイス別ステータス検索用
        Index('idx_csi_session_created', 'session_id', 'created_at'),  # セッション別時系列検索用
        Index('idx_csi_status_created', 'status', 'created_at'),  # ステータス別時系列検索用
    )

    # リレーション
    device = relationship("Device", back_populates="csi_data")
    breathing_analyses = relationship("BreathingAnalysis", back_populates="csi_data", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CSIData(id={self.id}, device_id={self.device_id}, status='{self.status}')>"


class Session(BaseModel):
    """セッションテーブル"""
    __tablename__ = "sessions"

    # デバイス関連
    device_id = Column(
        BaseModel.id.type,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # セッション情報
    session_name = Column(String(255), nullable=True)
    start_time = Column(BaseModel.created_at.type, nullable=False)
    end_time = Column(BaseModel.created_at.type, nullable=True)
    duration = Column(Integer, nullable=True)  # 秒単位

    # ステータス
    status = Column(String(50), default="active", nullable=False)  # active, completed, stopped, error

    # メタデータ
    meta_data = Column(JSONB, nullable=True)

    # リレーション
    device = relationship("Device", back_populates="sessions")

    def __repr__(self):
        return f"<Session(id={self.id}, device_id={self.device_id}, status='{self.status}')>"