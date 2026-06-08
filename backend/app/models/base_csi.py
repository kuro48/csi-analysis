import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class BaseCSI(Base):
    __tablename__ = "base_csi"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    fft_dataframe = Column(JSON, nullable=False)
    wavelet_dataframe = Column(JSON, nullable=True)
    music_dataframe = Column(JSON, nullable=True)
    source_pcap_path = Column(String(500), nullable=True)
    source_pcap_size = Column(Integer, nullable=True)
    # processing, completed, error
    status = Column(String(50), default="processing", nullable=False, index=True)
    error_message = Column(String(1000), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<BaseCSI(id={self.id}, name={self.name})>"

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "fft_dataframe": self.fft_dataframe,
            "wavelet_dataframe": self.wavelet_dataframe,
            "music_dataframe": self.music_dataframe,
            "source_pcap_path": self.source_pcap_path,
            "source_pcap_size": self.source_pcap_size,
            "status": self.status,
            "error_message": self.error_message,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
