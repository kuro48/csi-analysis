from sqlalchemy import JSON, BigInteger, Column, Index, String
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import BaseModel

# PostgreSQL では JSONB、それ以外（テスト用SQLite等）では JSON にフォールバック
_JSONB = JSON().with_variant(JSONB(), "postgresql")


class CSIData(BaseModel):
    __tablename__ = "csi_data"

    session_id = Column(String(255), nullable=True, index=True)
    raw_data = Column(_JSONB, nullable=True)
    processed_data = Column(_JSONB, nullable=True)
    file_path = Column(String(500), nullable=True)
    file_size = Column(BigInteger, nullable=True, index=True)
    device_id = Column(String(255), nullable=True, index=True)
    status = Column(String(50), default="received", nullable=False, index=True)

    blockchain_tx_hash = Column(String(66), nullable=True, index=True, comment="ブロックチェーントランザクションハッシュ")
    blockchain_status = Column(
        String(20), default="pending", nullable=False, index=True, comment="ブロックチェーン記録状態: pending, confirmed, failed"
    )
    blockchain_recorded_at = Column(BaseModel.created_at.type, nullable=True, comment="ブロックチェーン記録完了時刻")

    __table_args__ = (
        Index("idx_csi_session_created", "session_id", "created_at"),
        Index("idx_csi_status_created", "status", "created_at"),
        Index("idx_csi_device_status", "device_id", "status"),
        Index("idx_csi_blockchain_sync", "blockchain_status", "created_at"),
    )
