"""
デバイスモデル
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Device(BaseModel):
    """デバイステーブル"""

    __tablename__ = "devices"

    # 基本情報
    device_id = Column(String(255), unique=True, nullable=False, index=True)
    device_name = Column(String(255), nullable=False, index=True)  # 検索用インデックス追加
    device_type = Column(String(100), default="raspberry_pi", nullable=False, index=True)  # フィルタリング用
    location = Column(String(255), nullable=True, index=True)  # 位置検索用

    # 所有者関連
    owner_id = Column(
        BaseModel.id.type,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,  # 所有者別デバイス検索用
    )

    # ステータス
    is_active = Column(Boolean, default=True, nullable=False, index=True)  # アクティブ状態フィルタリング用
    last_seen = Column(DateTime(timezone=True), nullable=True, index=True)  # オンライン状態判定用

    # 複合インデックス - 頻繁に使用されるクエリパターン用
    __table_args__ = (
        Index("idx_device_status_lastseen", "is_active", "last_seen"),  # オンライン/オフライン判定用
        Index("idx_device_owner_active", "owner_id", "is_active"),  # 所有者のアクティブデバイス検索用
        Index("idx_device_type_location", "device_type", "location"),  # タイプ・場所での検索用
        Index("idx_device_created_active", "created_at", "is_active"),  # 作成日でのソート・フィルタリング用
    )

    # リレーション
    owner = relationship("User", back_populates="devices")
    csi_data = relationship("CSIData", back_populates="device", cascade="all, delete-orphan")
    breathing_analyses = relationship("BreathingAnalysis", back_populates="device", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="device", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="device", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Device(id={self.id}, device_id='{self.device_id}', name='{self.device_name}')>"
