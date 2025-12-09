"""
SQLAlchemy ベースモデル
"""

import uuid as uuid_pkg

from sqlalchemy import UUID, Column, DateTime
from sqlalchemy.sql import func

# app.core.database の Base を使用
from app.core.database import Base


class BaseModel(Base):
    """
    全モデルの基底クラス
    共通フィールドを定義
    """

    __abstract__ = True

    # 主キー（UUID）
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4, unique=True, nullable=False)

    # タイムスタンプ
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.id})>"
