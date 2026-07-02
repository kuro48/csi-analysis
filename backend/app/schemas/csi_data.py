import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel


class CSIDataUpload(BaseModel):
    session_id: Optional[str] = None
    file_name: str
    collection_start_time: Optional[datetime] = None
    collection_duration: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class CSIDataResponse(BaseModel):
    id: uuid.UUID
    session_id: Optional[str] = None
    device_id: Optional[str] = None
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
    session_id: Optional[str] = None
    status: Optional[str] = "all"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class CSIDataListResponse(BaseModel):
    csi_data: List[CSIDataResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProcessingStatus(BaseModel):
    status: str
    progress: Optional[float] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
