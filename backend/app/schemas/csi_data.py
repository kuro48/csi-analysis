"""
CSIデータ関連スキーマ
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field
import uuid


class CSIDataUpload(BaseModel):
    """CSIデータアップロード時のスキーマ"""
    session_id: Optional[str] = Field(None, description="セッションID")
    file_name: str = Field(..., description="ファイル名")
    collection_start_time: Optional[datetime] = Field(None, description="データ収集開始時刻")
    collection_duration: Optional[float] = Field(None, description="収集時間（秒）")
    metadata: Optional[Dict[str, Any]] = Field(None, description="追加メタデータ")


class CSIDataResponse(BaseModel):
    """CSIデータレスポンススキーマ"""
    id: uuid.UUID
    session_id: Optional[str] = None
    raw_data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
    processed_data: Optional[Dict[str, Any]] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    status: str

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CSIDataFilter(BaseModel):
    """CSIデータフィルタースキーマ"""
    session_id: Optional[str] = Field(None, description="セッションID")
    status: Optional[str] = Field("all", description="ステータス")
    start_date: Optional[datetime] = Field(None, description="開始日時")
    end_date: Optional[datetime] = Field(None, description="終了日時")


class CSIDataListResponse(BaseModel):
    """CSIデータ一覧レスポンススキーマ"""
    csi_data: List[CSIDataResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProcessingStatus(BaseModel):
    """処理状態スキーマ"""
    status: str = Field(..., description="処理状態")
    progress: Optional[float] = Field(None, description="進捗（0-1）")
    error_message: Optional[str] = Field(None, description="エラーメッセージ")
    started_at: Optional[datetime] = Field(None, description="処理開始時刻")
    completed_at: Optional[datetime] = Field(None, description="処理完了時刻")


# セッション関連スキーマ
class SessionCreate(BaseModel):
    """セッション作成スキーマ"""
    session_name: Optional[str] = Field(None, description="セッション名")
    start_time: datetime = Field(..., description="開始時刻")
    metadata: Optional[Dict[str, Any]] = Field(None, description="メタデータ")


class SessionUpdate(BaseModel):
    """セッション更新スキーマ"""
    session_name: Optional[str] = Field(None, description="セッション名")
    end_time: Optional[datetime] = Field(None, description="終了時刻")
    duration: Optional[int] = Field(None, description="継続時間（秒）")
    status: Optional[str] = Field(None, description="ステータス")
    metadata: Optional[Dict[str, Any]] = Field(None, description="メタデータ")


class SessionResponse(BaseModel):
    """セッションレスポンススキーマ"""
    id: uuid.UUID
    session_name: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    duration: Optional[int]
    status: str
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    class Config:
        from_attributes = True
