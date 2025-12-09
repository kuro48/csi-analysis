# """
# デバイス関連のPydanticスキーマ
# """

# from pydantic import BaseModel, Field, validator
# from typing import Optional, Literal
# from datetime import datetime
# import uuid as uuid_pkg
# import re


# class DeviceBase(BaseModel):
#     """デバイスベーススキーマ"""
#     device_name: str = Field(..., min_length=1, max_length=255, description="デバイス名")
#     location: Optional[str] = Field(None, max_length=255, description="設置場所")


# class DeviceCreate(DeviceBase):
#     """デバイス作成スキーマ"""
#     device_id: str = Field(..., min_length=3, max_length=100, description="デバイスID")

#     @validator('device_id')
#     def device_id_format(cls, v):
#         """デバイスIDの形式チェック"""
#         if not re.match(r'^[a-zA-Z0-9_-]+$', v):
#             raise ValueError('デバイスIDは英数字、アンダースコア、ハイフンのみ使用可能です')
#         return v

#     @validator('device_name')
#     def device_name_not_empty(cls, v):
#         """デバイス名の空文字チェック"""
#         if not v or not v.strip():
#             raise ValueError('デバイス名は必須です')
#         return v.strip()


# class DeviceUpdate(BaseModel):
#     """デバイス更新スキーマ"""
#     device_name: Optional[str] = Field(None, min_length=1, max_length=255)
#     device_type: Optional[Literal["raspberry_pi", "esp32", "other"]] = None
#     location: Optional[str] = Field(None, max_length=255)
#     is_active: Optional[bool] = None

#     @validator('device_name', pre=True)
#     def device_name_not_empty(cls, v):
#         """デバイス名の空文字チェック"""
#         if v is not None and (not v or not v.strip()):
#             raise ValueError('デバイス名が指定された場合は空文字にできません')
#         return v.strip() if v else v


# class DeviceResponse(DeviceBase):
#     """デバイス応答スキーマ"""
#     id: uuid_pkg.UUID
#     device_id: str = Field(..., description="デバイスID")
#     owner_id: Optional[uuid_pkg.UUID]
#     is_active: bool
#     last_seen: Optional[datetime]
#     created_at: datetime
#     updated_at: datetime

#     # 状態情報（計算フィールド）
#     status: str = Field(default="unknown", description="デバイス状態")
#     connection_status: str = Field(default="offline", description="接続状態")
#     device_token: Optional[str] = Field(None, description="デバイストークン（登録時のみ）")

#     class Config:
#         from_attributes = True


# class DeviceStatus(BaseModel):
#     """デバイス状態スキーマ"""
#     status: Literal["online", "offline", "error", "maintenance"]
#     last_seen: Optional[datetime]
#     connection_status: str
#     uptime_minutes: Optional[int] = None
#     last_heartbeat: Optional[datetime] = None
#     error_message: Optional[str] = None


# class DeviceHeartbeat(BaseModel):
#     """デバイスハートビートスキーマ"""
#     status: Literal["online", "error"] = "online"
#     message: Optional[str] = None
#     metadata: Optional[dict] = None


# class DeviceListResponse(BaseModel):
#     """デバイス一覧応答スキーマ"""
#     devices: list[DeviceResponse]
#     total: int
#     page: int
#     page_size: int
#     total_pages: int


# class DeviceFilter(BaseModel):
#     """デバイスフィルター用スキーマ"""
#     status: Optional[Literal["online", "offline", "error", "all"]] = "all"
#     device_type: Optional[Literal["raspberry_pi", "esp32", "other", "all"]] = "all"
#     location: Optional[str] = None
#     search: Optional[str] = None
#     is_active: Optional[bool] = None
#     owner_id: Optional[uuid_pkg.UUID] = None


# class DeviceSort(BaseModel):
#     """デバイスソート用スキーマ"""
#     field: Literal["device_name", "device_id", "location", "last_seen", "created_at"] = "created_at"
#     order: Literal["asc", "desc"] = "desc"


# class DevicePagination(BaseModel):
#     """ページネーション用スキーマ"""
#     page: int = Field(default=1, ge=1, description="ページ番号")
#     page_size: int = Field(default=20, ge=1, le=100, description="1ページあたりの件数")


# class DeviceStatistics(BaseModel):
#     """デバイス統計スキーマ"""
#     total_devices: int
#     online_devices: int
#     offline_devices: int
#     error_devices: int
#     by_type: dict[str, int]
#     by_location: dict[str, int]
#     recent_activity: list[dict]