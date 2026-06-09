"""
ベースCSIスキーマ定義
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


class BaseCSIRegister(BaseModel):
    """ベースCSI登録リクエスト"""
    name: str = Field(..., description="ベースCSI名（例: 正常呼吸パターン1）")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "正常呼吸パターン - 安静時"
            }
        }


class BaseCSIResponse(BaseModel):
    """ベースCSIレスポンス"""
    id: str
    name: str
    fft_dataframe: Optional[Dict[str, Any]] = None
    wavelet_dataframe: Optional[Dict[str, Any]] = None
    music_dataframe: Optional[Dict[str, Any]] = None
    subcarrier_medians: Optional[Dict[str, float]] = None
    source_pcap_path: Optional[str]
    source_pcap_size: Optional[int]
    status: str
    error_message: Optional[str]
    expires_at: Optional[str]
    is_expired: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "正常呼吸パターン - 安静時",
                "source_pcap_path": "/data/pcap/base_csi_123.pcap",
                "source_pcap_size": 1048576,
                "status": "completed",
                "error_message": None,
                "expires_at": "2024-12-31T23:59:59",
                "is_expired": False,
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }


class BaseCSIListResponse(BaseModel):
    """ベースCSI一覧レスポンス"""
    base_csis: List[BaseCSIResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    class Config:
        json_schema_extra = {
            "example": {
                "base_csis": [],
                "total": 10,
                "page": 1,
                "page_size": 20,
                "total_pages": 1
            }
        }


class BaseCSIUpdate(BaseModel):
    """ベースCSI更新リクエスト"""
    name: Optional[str] = Field(None, description="ベースCSI名")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "正常呼吸パターン - 安静時（更新版）"
            }
        }


class CSISimilarityResult(BaseModel):
    """CSI類似度比較結果"""
    base_csi_id: str
    base_csi_name: str
    similarity_score: float = Field(..., description="コサイン類似度スコア（0.0-1.0）")
    zkp_proof: Dict[str, Any] = Field(..., description="ZKP証明")
    public_signals: List[int] = Field(..., description="公開信号")
    best_candidate_index: int = Field(..., description="最適候補インデックス")

    class Config:
        json_schema_extra = {
            "example": {
                "base_csi_id": "123e4567-e89b-12d3-a456-426614174000",
                "base_csi_name": "正常呼吸パターン - 安静時",
                "similarity_score": 0.95,
                "zkp_proof": {},
                "public_signals": [0, 9500],
                "best_candidate_index": 0
            }
        }
