"""
ベースCSIデータモデル

基準となるCSIデータ（正常な呼吸パターン等）を保存するモデル
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

class BaseCSI(Base):
    """ベースCSIデータモデル"""

    __tablename__ = "base_csi"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 基本情報
    name = Column(String(255), nullable=False, comment="ベースCSIの名前（例: 正常呼吸パターン1）")

    # FFTデータ（周波数解析結果）
    fft_dataframe = Column(JSON, nullable=False, comment="FFT DataFrame（周波数ビン × サブキャリア）")

    # 元のPCAPファイル情報
    source_pcap_path = Column(String(500), nullable=True, comment="元のPCAPファイルパス")
    source_pcap_size = Column(Integer, nullable=True, comment="元のPCAPファイルサイズ（バイト）")

    # 処理状態
    status = Column(String(50), default="processing", nullable=False, index=True, comment="processing, completed, error")
    error_message = Column(String(1000), nullable=True, comment="処理失敗時のエラーメッセージ")

    # 有効期限
    expires_at = Column(DateTime, comment="有効期限")

    # タイムスタンプ
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<BaseCSI(id={self.id}, name={self.name})>"

    def is_expired(self) -> bool:
        """有効期限切れかどうかを判定"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def to_dict(self):
        """辞書形式に変換"""
        return {
            "id": str(self.id),
            "name": self.name,
            "source_pcap_path": self.source_pcap_path,
            "source_pcap_size": self.source_pcap_size,
            "status": self.status,
            "error_message": self.error_message,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
