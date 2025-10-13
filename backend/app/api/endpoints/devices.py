"""
デバイス管理関連エンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import math

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.device import DeviceService
from app.schemas.device import (
    DeviceCreate, DeviceUpdate, DeviceResponse, DeviceListResponse,
    DeviceFilter, DeviceSort, DevicePagination, DeviceStatus,
    DeviceHeartbeat, DeviceStatistics
)

router = APIRouter()


@router.get("/", response_model=DeviceListResponse)
async def list_devices(
    # フィルター関連
    status: Optional[str] = Query("all", description="デバイス状態フィルター"),
    device_type: Optional[str] = Query("all", description="デバイスタイプフィルター"),
    location: Optional[str] = Query(None, description="場所フィルター"),
    search: Optional[str] = Query(None, description="検索キーワード"),
    is_active: Optional[bool] = Query(None, description="アクティブ状態フィルター"),

    # ソート関連
    sort_field: Optional[str] = Query("created_at", description="ソートフィールド"),
    sort_order: Optional[str] = Query("desc", description="ソート順"),

    # ページネーション
    page: int = Query(1, ge=1, description="ページ番号"),
    page_size: int = Query(20, ge=1, le=100, description="1ページあたりの件数"),

    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    デバイス一覧取得
    """
    # フィルター構築
    filters = DeviceFilter(
        status=status,
        device_type=device_type,
        location=location,
        search=search,
        is_active=is_active
    )

    # ソート構築
    sort = DeviceSort(field=sort_field, order=sort_order)

    # ページネーション構築
    pagination = DevicePagination(page=page, page_size=page_size)

    try:
        devices, total_count = DeviceService.get_devices(
            db,
            user_id=current_user.id,
            filters=filters,
            sort=sort,
            pagination=pagination
        )

        # レスポンス用にデバイスデータを変換
        device_responses = []
        for device in devices:
            status_info = DeviceService.get_device_status(db, device.device_id)
            device_response = DeviceResponse(
                id=device.id,
                device_id=device.device_id,
                device_name=device.device_name,
                device_type=device.device_type,
                location=device.location,
                owner_id=device.owner_id,
                is_active=device.is_active,
                last_seen=device.last_seen,
                created_at=device.created_at,
                updated_at=device.updated_at,
                status=status_info.status if status_info else "unknown",
                connection_status=status_info.connection_status if status_info else "offline"
            )
            device_responses.append(device_response)

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

        return DeviceListResponse(
            devices=device_responses,
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"デバイス一覧の取得に失敗しました: {str(e)}"
        )


@router.post("/register", response_model=DeviceResponse)
async def register_device(
    device_data: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    デバイス登録（/registerエンドポイント）
    """
    try:
        device = await DeviceService.create_device(db, device_data, current_user.id)
        status_info = DeviceService.get_device_status(db, device.device_id)

        return DeviceResponse(
            id=device.id,
            device_id=device.device_id,
            device_name=device.device_name,
            device_type=device.device_type,
            location=device.location,
            owner_id=device.owner_id,
            is_active=device.is_active,
            last_seen=device.last_seen,
            created_at=device.created_at,
            updated_at=device.updated_at,
            status=status_info.status if status_info else "unknown",
            connection_status=status_info.connection_status if status_info else "offline"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"デバイス作成に失敗しました: {str(e)}"
        )


@router.post("/", response_model=DeviceResponse)
async def create_device(
    device_data: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    デバイス登録
    """
    try:
        device = await DeviceService.create_device(db, device_data, current_user.id)
        status_info = DeviceService.get_device_status(db, device.device_id)

        return DeviceResponse(
            id=device.id,
            device_id=device.device_id,
            device_name=device.device_name,
            device_type=device.device_type,
            location=device.location,
            owner_id=device.owner_id,
            is_active=device.is_active,
            last_seen=device.last_seen,
            created_at=device.created_at,
            updated_at=device.updated_at,
            status=status_info.status if status_info else "unknown",
            connection_status=status_info.connection_status if status_info else "offline"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"デバイス作成に失敗しました: {str(e)}"
        )


@router.get("/{device_uuid}", response_model=DeviceResponse)
async def get_device(
    device_uuid: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    特定デバイス情報取得
    """
    device = DeviceService.get_device_by_uuid(db, device_uuid, current_user.id)
    if not device:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="デバイスが見つかりません"
        )

    status_info = DeviceService.get_device_status(db, device.device_id)

    return DeviceResponse(
        id=device.id,
        device_id=device.device_id,
        device_name=device.device_name,
        device_type=device.device_type,
        location=device.location,
        owner_id=device.owner_id,
        is_active=device.is_active,
        last_seen=device.last_seen,
        created_at=device.created_at,
        updated_at=device.updated_at,
        status=status_info.status if status_info else "unknown",
        connection_status=status_info.connection_status if status_info else "offline"
    )


@router.put("/{device_uuid}", response_model=DeviceResponse)
async def update_device(
    device_uuid: uuid.UUID,
    device_update: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    デバイス情報更新
    """
    device = await DeviceService.update_device(db, device_uuid, device_update, current_user.id)
    if not device:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="デバイスが見つかりません"
        )

    status_info = DeviceService.get_device_status(db, device.device_id)

    return DeviceResponse(
        id=device.id,
        device_id=device.device_id,
        device_name=device.device_name,
        device_type=device.device_type,
        location=device.location,
        owner_id=device.owner_id,
        is_active=device.is_active,
        last_seen=device.last_seen,
        created_at=device.created_at,
        updated_at=device.updated_at,
        status=status_info.status if status_info else "unknown",
        connection_status=status_info.connection_status if status_info else "offline"
    )


@router.delete("/{device_uuid}")
async def delete_device(
    device_uuid: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    デバイス削除
    """
    success = await DeviceService.delete_device(db, device_uuid, current_user.id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="デバイスが見つかりません"
        )

    return {"message": "デバイスが正常に削除されました"}


@router.post("/{device_id}/heartbeat", response_model=DeviceResponse)
async def device_heartbeat(
    device_id: str,
    heartbeat_data: DeviceHeartbeat,
    db: Session = Depends(get_db)
):
    """
    デバイスハートビート受信
    """
    # デバイスIDの整合性チェック
    if heartbeat_data.device_id != device_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="URLのデバイスIDとリクエストボディのデバイスIDが一致しません"
        )

    try:
        device = await DeviceService.update_heartbeat(db, heartbeat_data)
        if not device:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="デバイスが見つかりません"
            )

        status_info = DeviceService.get_device_status(db, device.device_id)

        return DeviceResponse(
            id=device.id,
            device_id=device.device_id,
            device_name=device.device_name,
            device_type=device.device_type,
            location=device.location,
            owner_id=device.owner_id,
            is_active=device.is_active,
            last_seen=device.last_seen,
            created_at=device.created_at,
            updated_at=device.updated_at,
            status=status_info.status if status_info else "unknown",
            connection_status=status_info.connection_status if status_info else "offline"
        )

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ハートビート処理に失敗しました: {str(e)}"
        )


@router.get("/{device_id}/status", response_model=DeviceStatus)
async def get_device_status(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    デバイス状態取得
    """
    # デバイスの存在確認と所有者チェック
    device = DeviceService.get_device(db, device_id, current_user.id)
    if not device:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="デバイスが見つかりません"
        )

    status_info = DeviceService.get_device_status(db, device_id)
    if not status_info:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="デバイス状態の取得に失敗しました"
        )

    return status_info


@router.get("/statistics/summary", response_model=dict)
async def get_device_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    デバイス統計情報取得
    """
    try:
        statistics = await DeviceService.get_device_statistics(db, current_user.id, broadcast=False)
        return statistics
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"統計情報の取得に失敗しました: {str(e)}"
        )