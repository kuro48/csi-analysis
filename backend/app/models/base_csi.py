"""
ベースCSIデータモデル

基準となるCSIデータ（正常な呼吸パターン等）を保存するモデル
"""

import uuid
from datetime import datetime, timedelta
from sqlalchemy import Column, String, DateTime, Integer, Text, JSON, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class BaseCSI(Base):
    """ベースCSIデータモデル"""

    __tablename__ = "base_csi"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # 基本情報
    name = Column(String(255), nullable=False, comment="ベースCSIの名前（例: 正常呼吸パターン1）")
    description = Column(Text, nullable=True, comment="説明")

    # FFTデータ（周波数解析結果）
    fft_dataframe = Column(JSON, nullable=False, comment="FFT DataFrame（周波数ビン × サブキャリア）")

    # 呼吸解析結果
    breathing_frequency_hz = Column(Float, nullable=True, comment="呼吸周波数（Hz）")
    confidence_score = Column(Float, nullable=True, comment="信頼度スコア（0.0-1.0）")
    best_subcarrier_indices = Column(JSON, nullable=True, comment="最適サブキャリアインデックス[4]")

    # 4次元ベクトル（コサイン類似度計算用）
    reference_vector = Column(JSON, nullable=False, comment="4次元参照ベクトル（ZKP用）")

    # 元のPCAPファイル情報
    source_pcap_path = Column(String(500), nullable=True, comment="元のPCAPファイルパス")
    source_pcap_size = Column(Integer, nullable=True, comment="元のPCAPファイルサイズ（バイト）")

    # 有効期限
    expires_at = Column(DateTime, nullable=True, comment="有効期限（Noneの場合は無期限）")

    # タイムスタンプ
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # リレーション
    user = relationship("User", back_populates="base_csis")

    def __repr__(self):
        return f"<BaseCSI(id={self.id}, name={self.name}, user_id={self.user_id})>"

    def is_expired(self) -> bool:
        """有効期限切れかどうかを判定"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def to_dict(self):
        """辞書形式に変換"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "name": self.name,
            "description": self.description,
            "breathing_frequency_hz": self.breathing_frequency_hz,
            "confidence_score": self.confidence_score,
            "best_subcarrier_indices": self.best_subcarrier_indices,
            "reference_vector": self.reference_vector,
            "source_pcap_path": self.source_pcap_path,
            "source_pcap_size": self.source_pcap_size,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
