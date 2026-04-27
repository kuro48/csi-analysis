from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field
import uuid


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


class SessionCreate(BaseModel):
    session_name: Optional[str] = None
    start_time: datetime
    metadata: Optional[Dict[str, Any]] = None


class SessionUpdate(BaseModel):
    session_name: Optional[str] = None
    end_time: Optional[datetime] = None
    duration: Optional[int] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SessionResponse(BaseModel):
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
