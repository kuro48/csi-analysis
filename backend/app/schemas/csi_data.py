"""
CSIデータ関連スキーマ
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field, validator
import uuid


class CSIDataUpload(BaseModel):
    """CSIデータアップロード時のスキーマ"""
    device_id: str = Field(..., description="デバイスID")
    session_id: Optional[str] = Field(None, description="セッションID")
    file_name: str = Field(..., description="ファイル名")
    collection_start_time: Optional[datetime] = Field(None, description="データ収集開始時刻")
    collection_duration: Optional[float] = Field(None, description="収集時間（秒）")
    metadata: Optional[Dict[str, Any]] = Field(None, description="追加メタデータ")

    @validator('device_id')
    def validate_device_id(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('デバイスIDは必須です')
        return v.strip()


class CSIDataResponse(BaseModel):
    """CSIデータレスポンススキーマ"""
    id: uuid.UUID
    device_id: str
    session_id: Optional[str]
    raw_data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]
    processed_data: Optional[Dict[str, Any]]
    file_path: Optional[str]
    file_size: Optional[int]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CSIDataFilter(BaseModel):
    """CSIデータフィルタースキーマ"""
    device_id: Optional[str] = Field(None, description="デバイスID")
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
    device_id: str = Field(..., description="デバイスID")
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
    device_id: str
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


# 呼吸解析関連スキーマ
class BreathingAnalysisResult(BaseModel):
    """呼吸解析結果スキーマ"""
    breathing_rate: Optional[float] = Field(None, description="呼吸数（回/分）")
    confidence_score: Optional[float] = Field(None, description="信頼度スコア")
    analysis_timestamp: datetime = Field(..., description="解析時刻")
    window_start: Optional[datetime] = Field(None, description="解析ウィンドウ開始")
    window_end: Optional[datetime] = Field(None, description="解析ウィンドウ終了")
    frequency_domain_data: Optional[Dict[str, Any]] = Field(None, description="周波数域データ")
    time_domain_data: Optional[Dict[str, Any]] = Field(None, description="時間域データ")
    quality_metrics: Optional[Dict[str, Any]] = Field(None, description="品質メトリクス")

    @validator('confidence_score')
    def validate_confidence_score(cls, v):
        if v is not None and (v < 0 or v > 1):
            raise ValueError('信頼度スコアは0-1の範囲である必要があります')
        return v

    @validator('breathing_rate')
    def validate_breathing_rate(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError('呼吸数は0-100の範囲である必要があります')
        return v


class BreathingAnalysisResponse(BaseModel):
    """呼吸解析レスポンススキーマ"""
    id: uuid.UUID
    csi_data_id: uuid.UUID
    device_id: str
    breathing_rate: Optional[float]
    confidence_score: Optional[float]
    analysis_timestamp: datetime
    window_start: Optional[datetime]
    window_end: Optional[datetime]
    frequency_domain_data: Optional[Dict[str, Any]]
    time_domain_data: Optional[Dict[str, Any]]
    quality_metrics: Optional[Dict[str, Any]]
    ipfs_hash: Optional[str]
    blockchain_tx_hash: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BreathingAnalysisFilter(BaseModel):
    """呼吸解析フィルタースキーマ"""
    device_id: Optional[str] = Field(None, description="デバイスID")
    start_date: Optional[datetime] = Field(None, description="開始日時")
    end_date: Optional[datetime] = Field(None, description="終了日時")
    min_confidence: Optional[float] = Field(None, description="最小信頼度")

    @validator('min_confidence')
    def validate_min_confidence(cls, v):
        if v is not None and (v < 0 or v > 1):
            raise ValueError('最小信頼度は0-1の範囲である必要があります')
        return v


class BreathingAnalysisListResponse(BaseModel):
    """呼吸解析一覧レスポンススキーマ"""
    analyses: List[BreathingAnalysisResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class BreathingAnalysisStats(BaseModel):
    """呼吸解析統計スキーマ"""
    device_id: str
    total_analyses: int
    avg_breathing_rate: Optional[float]
    avg_confidence_score: Optional[float]
    latest_analysis: Optional[datetime]
    analysis_period_start: Optional[datetime]
    analysis_period_end: Optional[datetime]


# アラート関連スキーマ
class AlertCreate(BaseModel):
    """アラート作成スキーマ"""
    device_id: str = Field(..., description="デバイスID")
    alert_type: str = Field(..., description="アラート種別")
    severity: str = Field("medium", description="重要度")
    message: Optional[str] = Field(None, description="アラートメッセージ")


class AlertResponse(BaseModel):
    """アラートレスポンススキーマ"""
    id: uuid.UUID
    device_id: str
    alert_type: str
    severity: str
    message: Optional[str]
    is_acknowledged: bool
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True