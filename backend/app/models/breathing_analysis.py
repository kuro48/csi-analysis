"""
呼吸解析結果モデル
"""

from sqlalchemy import Column, String, Boolean, Numeric, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import BaseModel


class BreathingAnalysis(BaseModel):
    """呼吸解析結果テーブル"""
    __tablename__ = "breathing_analysis"

    # 関連データ
    csi_data_id = Column(
        BaseModel.id.type,
        ForeignKey("csi_data.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    # device_id = Column(
    #     BaseModel.id.type,
    #     ForeignKey("devices.id", ondelete="CASCADE"),
    #     nullable=False,
    #     index=True
    # )

    # 解析結果
    breathing_rate = Column(Numeric(5, 2), nullable=True, index=True)  # 呼吸率検索用
    confidence_score = Column(Numeric(5, 4), nullable=True, index=True)  # 信頼度検索用

    # 解析時間範囲
    analysis_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    window_start = Column(DateTime(timezone=True), nullable=True, index=True)
    window_end = Column(DateTime(timezone=True), nullable=True, index=True)

    # 詳細解析データ
    frequency_domain_data = Column(JSONB, nullable=True)  # 周波数域データ
    time_domain_data = Column(JSONB, nullable=True)       # 時間域データ
    quality_metrics = Column(JSONB, nullable=True)        # 品質メトリクス

    # 外部ストレージ連携
    ipfs_hash = Column(String(255), nullable=True, index=True)        # IPFS検索用
    blockchain_tx_hash = Column(String(255), nullable=True, index=True)  # ブロックチェーン検索用

    # 複合インデックス - 呼吸解析固有のクエリパターン用
    __table_args__ = (
        # Index('idx_breathing_device_timestamp', 'device_id', 'analysis_timestamp'),  # デバイス別時系列検索用
        # Index('idx_breathing_device_rate', 'device_id', 'breathing_rate'),  # デバイス別呼吸率検索用
        Index('idx_breathing_timestamp_rate', 'analysis_timestamp', 'breathing_rate'),  # 時系列呼吸率検索用
        Index('idx_breathing_confidence_rate', 'confidence_score', 'breathing_rate'),  # 信頼度・呼吸率相関検索用
        Index('idx_breathing_window', 'window_start', 'window_end'),  # ウィンドウ範囲検索用
    )

    # リレーション
    csi_data = relationship("CSIData", back_populates="breathing_analyses")
    # device = relationship("Device", back_populates="breathing_analyses")

    # def __repr__(self):
    #     return f"<BreathingAnalysis(id={self.id}, device_id={self.device_id}, rate={self.breathing_rate})>"


# class Alert(BaseModel):
#     """アラート/通知テーブル"""
#     __tablename__ = "alerts"

#     # デバイス関連
#     device_id = Column(
#         BaseModel.id.type,
#         ForeignKey("devices.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True
#     )

#     # アラート情報
#     alert_type = Column(String(100), nullable=False, index=True)  # breathing_anomaly, device_offline, etc.
#     severity = Column(String(50), default="medium", nullable=False, index=True)  # 重要度検索用
#     message = Column(Text, nullable=True)

#     # 確認状態
#     is_acknowledged = Column(Boolean, default=False, nullable=False, index=True)  # 未確認アラート検索用
#     acknowledged_by = Column(
#         BaseModel.id.type,
#         ForeignKey("users.id", ondelete="SET NULL"),
#         nullable=True,
#         index=True  # 確認者検索用
#     )
#     acknowledged_at = Column(DateTime(timezone=True), nullable=True, index=True)  # 確認日時検索用

#     # 複合インデックス - アラート固有のクエリパターン用
#     __table_args__ = (
#         Index('idx_alert_device_created', 'device_id', 'created_at'),  # デバイス別時系列検索用
#         Index('idx_alert_type_severity', 'alert_type', 'severity'),  # タイプ・重要度検索用
#         Index('idx_alert_acknowledged_created', 'is_acknowledged', 'created_at'),  # 未確認アラート検索用
#         Index('idx_alert_severity_created', 'severity', 'created_at'),  # 重要度別時系列検索用
#     )

#     # リレーション
#     device = relationship("Device", back_populates="alerts")
#     acknowledged_user = relationship("User")

#     def __repr__(self):
#         return f"<Alert(id={self.id}, type='{self.alert_type}', severity='{self.severity}')>"