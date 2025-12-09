"""
デバイス管理関連のサービス機能
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import and_, asc, desc, func, or_
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.user import User
from app.schemas.device import (
    DeviceCreate,
    DeviceFilter,
    DeviceHeartbeat,
    DevicePagination,
    DeviceSort,
    DeviceStatus,
    DeviceUpdate,
)
from app.services.cache import DeviceCacheService
from app.services.websocket import realtime_service


class DeviceService:
    """デバイス管理サービス"""

    @staticmethod
    async def create_device(db: Session, device_data: DeviceCreate, owner_id: uuid.UUID) -> Device:
        """新規デバイス作成"""
        # デバイスIDの重複チェック
        existing_device = db.query(Device).filter(Device.device_id == device_data.device_id).first()
        if existing_device:
            raise ValueError(f"デバイスID '{device_data.device_id}' は既に使用されています")

        # デバイス作成
        db_device = Device(
            device_id=device_data.device_id,
            device_name=device_data.device_name,
            device_type=device_data.device_type,
            location=device_data.location,
            owner_id=owner_id,
            is_active=True,
            last_seen=datetime.now(timezone.utc),
        )

        db.add(db_device)
        db.commit()
        db.refresh(db_device)

        # WebSocketで新規デバイス作成を通知
        await realtime_service.broadcast_device_status_update(
            db_device.device_id,
            {
                "type": "device_created",
                "id": str(db_device.id),
                "device_id": db_device.device_id,
                "device_name": db_device.device_name,
                "device_type": db_device.device_type,
                "location": db_device.location,
                "status": "offline",
                "connection_status": "disconnected",
                "last_seen": db_device.last_seen.isoformat() if db_device.last_seen else None,
                "created_at": db_device.created_at.isoformat(),
            },
        )

        return db_device

    @staticmethod
    def get_device(db: Session, device_id: str, user_id: uuid.UUID = None) -> Optional[Device]:
        """デバイス取得"""
        query = db.query(Device).filter(Device.device_id == device_id)

        # ユーザーIDが指定されている場合は所有者チェック
        if user_id:
            query = query.filter(Device.owner_id == user_id)

        return query.first()

    @staticmethod
    def get_device_by_uuid(db: Session, device_uuid: uuid.UUID, user_id: uuid.UUID = None) -> Optional[Device]:
        """UUID でデバイス取得"""
        query = db.query(Device).filter(Device.id == device_uuid)

        if user_id:
            query = query.filter(Device.owner_id == user_id)

        return query.first()

    @staticmethod
    def get_devices(
        db: Session,
        user_id: uuid.UUID = None,
        filters: DeviceFilter = None,
        sort: DeviceSort = None,
        pagination: DevicePagination = None,
        cache_service: Optional[DeviceCacheService] = None,
    ) -> Tuple[List[Device], int]:
        """デバイス一覧取得（キャッシュ対応）"""

        # キャッシュキー生成
        if cache_service and user_id:
            filter_dict = {
                "user_id": str(user_id),
                "filters": filters.dict() if filters else {},
                "sort": sort.dict() if sort else {},
                "pagination": pagination.dict() if pagination else {},
            }
            filters_hash = hashlib.md5(json.dumps(filter_dict, sort_keys=True).encode()).hexdigest()

            # キャッシュから取得を試行
            cached_data = cache_service.get_devices_list(str(user_id), filters_hash)
            if cached_data:
                return cached_data["devices"], cached_data["total_count"]

        query = db.query(Device)

        # 所有者フィルター
        if user_id:
            query = query.filter(Device.owner_id == user_id)

        # フィルター適用（パフォーマンス最適化版）
        if filters:
            # インデックス効果最大化：選択性の高いフィルタを最初に適用
            if filters.is_active is not None:
                query = query.filter(Device.is_active == filters.is_active)

            if filters.device_type and filters.device_type != "all":
                query = query.filter(Device.device_type == filters.device_type)

            # 状態フィルター（最も重要なフィルタ）
            if filters.status and filters.status != "all":
                now = datetime.now(timezone.utc)
                cutoff_time = now - timedelta(minutes=5)

                if filters.status == "online":
                    # インデックス活用：is_active, last_seen順でフィルタ
                    query = query.filter(and_(Device.is_active == True, Device.last_seen > cutoff_time))
                elif filters.status == "offline":
                    # インデックス活用を考慮した最適化
                    query = query.filter(
                        or_(
                            Device.is_active == False,
                            and_(
                                Device.is_active == True,
                                or_(Device.last_seen < cutoff_time, Device.last_seen.is_(None)),
                            ),
                        )
                    )

            # 位置フィルタ（インデックス活用）
            if filters.location:
                query = query.filter(Device.location.ilike(f"%{filters.location}%"))

            # テキスト検索は最後に適用（コストが高いため）
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.filter(
                    or_(
                        Device.device_name.ilike(search_term),
                        Device.device_id.ilike(search_term),
                        Device.location.ilike(search_term),
                    )
                )

        # カウントクエリの最適化：ページネーションがある場合は効率的にカウント
        from sqlalchemy import func

        if pagination and pagination.page > 1:
            # 別途カウント専用クエリを実行
            count_query = db.query(func.count(Device.id))

            # フィルター条件をカウントクエリにも適用
            if user_id:
                count_query = count_query.filter(Device.owner_id == user_id)

            if filters:
                if filters.is_active is not None:
                    count_query = count_query.filter(Device.is_active == filters.is_active)
                if filters.device_type and filters.device_type != "all":
                    count_query = count_query.filter(Device.device_type == filters.device_type)
                if filters.status and filters.status != "all":
                    now = datetime.now(timezone.utc)
                    cutoff_time = now - timedelta(minutes=5)
                    if filters.status == "online":
                        count_query = count_query.filter(and_(Device.is_active == True, Device.last_seen > cutoff_time))
                    elif filters.status == "offline":
                        count_query = count_query.filter(
                            or_(
                                Device.is_active == False,
                                and_(
                                    Device.is_active == True,
                                    or_(Device.last_seen < cutoff_time, Device.last_seen.is_(None)),
                                ),
                            )
                        )
                if filters.location:
                    count_query = count_query.filter(Device.location.ilike(f"%{filters.location}%"))
                if filters.search:
                    search_term = f"%{filters.search}%"
                    count_query = count_query.filter(
                        or_(
                            Device.device_name.ilike(search_term),
                            Device.device_id.ilike(search_term),
                            Device.location.ilike(search_term),
                        )
                    )

            total_count = count_query.scalar()

            # データがない場合は早期リターン
            if total_count == 0:
                return [], 0
        else:
            total_count = query.count()

        # ソート
        if sort:
            if sort.field == "device_name":
                order_column = Device.device_name
            elif sort.field == "device_id":
                order_column = Device.device_id
            elif sort.field == "location":
                order_column = Device.location
            elif sort.field == "last_seen":
                order_column = Device.last_seen
            else:  # created_at
                order_column = Device.created_at

            if sort.order == "asc":
                query = query.order_by(asc(order_column))
            else:
                query = query.order_by(desc(order_column))

        # ページネーション
        if pagination:
            offset = (pagination.page - 1) * pagination.page_size
            query = query.offset(offset).limit(pagination.page_size)

        devices = query.all()

        # キャッシュに保存
        if cache_service and user_id:
            cache_data = {
                "devices": [
                    (
                        device.dict()
                        if hasattr(device, "dict")
                        else {
                            "id": str(device.id),
                            "device_id": device.device_id,
                            "device_name": device.device_name,
                            "device_type": device.device_type,
                            "location": device.location,
                            "is_active": device.is_active,
                            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                            "created_at": device.created_at.isoformat(),
                            "updated_at": device.updated_at.isoformat(),
                        }
                    )
                    for device in devices
                ],
                "total_count": total_count,
            }
            cache_service.set_devices_list(str(user_id), filters_hash, cache_data)

        return devices, total_count

    @staticmethod
    async def update_device(
        db: Session, device_uuid: uuid.UUID, device_update: DeviceUpdate, user_id: uuid.UUID = None
    ) -> Optional[Device]:
        """デバイス更新"""
        # デバイス取得（所有者チェック含む）
        device = DeviceService.get_device_by_uuid(db, device_uuid, user_id)
        if not device:
            return None

        # 更新データを適用
        update_data = device_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(device, field, value)

        device.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(device)

        # WebSocketでデバイス更新を通知
        status = DeviceService.get_device_status(db, device.device_id)
        await realtime_service.notify_device_updated(
            {
                "id": str(device.id),
                "device_id": device.device_id,
                "device_name": device.device_name,
                "device_type": device.device_type,
                "location": device.location,
                "status": status.status if status else "offline",
                "connection_status": status.connection_status if status else "disconnected",
                "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                "is_active": device.is_active,
                "updated_at": device.updated_at.isoformat(),
            }
        )

        return device

    @staticmethod
    async def delete_device(db: Session, device_uuid: uuid.UUID, user_id: uuid.UUID = None) -> bool:
        """デバイス削除"""
        device = DeviceService.get_device_by_uuid(db, device_uuid, user_id)
        if not device:
            return False

        device_id = device.device_id  # 削除前に保存

        db.delete(device)
        db.commit()

        # WebSocketでデバイス削除を通知
        await realtime_service.notify_device_deleted(device_id)

        return True

    @staticmethod
    async def update_heartbeat(db: Session, heartbeat_data: DeviceHeartbeat) -> Optional[Device]:
        """デバイスハートビート更新"""
        device = DeviceService.get_device(db, heartbeat_data.device_id)
        if not device:
            return None

        # 前回の状態を記録
        previous_last_seen = device.last_seen
        previous_status = DeviceService.get_device_status(db, device.device_id)

        # ハートビート情報を更新
        device.last_seen = datetime.now(timezone.utc)
        device.is_active = True

        # メタデータがある場合は更新
        if heartbeat_data.metadata:
            device.metadata = {
                **(device.metadata or {}),
                **heartbeat_data.metadata,
                "last_heartbeat": device.last_seen.isoformat(),
            }

        db.commit()
        db.refresh(device)

        # 新しい状態を取得
        current_status = DeviceService.get_device_status(db, device.device_id)

        # WebSocketでハートビート通知
        await realtime_service.broadcast_device_heartbeat(
            device.device_id,
            {
                "device_id": device.device_id,
                "device_name": device.device_name,
                "status": current_status.status if current_status else "offline",
                "connection_status": current_status.connection_status if current_status else "disconnected",
                "last_seen": device.last_seen.isoformat(),
                "message": heartbeat_data.message,
                "metadata": heartbeat_data.metadata,
            },
        )

        # 状態が変更された場合は状態変更通知
        if (not previous_status) or (current_status and previous_status.status != current_status.status):
            await realtime_service.broadcast_device_status(
                {
                    "id": str(device.id),
                    "device_id": device.device_id,
                    "device_name": device.device_name,
                    "device_type": device.device_type,
                    "location": device.location,
                    "status": current_status.status if current_status else "offline",
                    "connection_status": current_status.connection_status if current_status else "disconnected",
                    "last_seen": device.last_seen.isoformat(),
                    "is_active": device.is_active,
                    "previous_status": previous_status.status if previous_status else "offline",
                }
            )

        return device

    @staticmethod
    def get_device_status(db: Session, device_id: str) -> Optional[DeviceStatus]:
        """デバイス状態取得"""
        device = DeviceService.get_device(db, device_id)
        if not device:
            return None

        now = datetime.now(timezone.utc)

        # 接続状態判定
        if device.last_seen:
            time_diff = now - device.last_seen
            if time_diff.total_seconds() < 300:  # 5分以内
                connection_status = "online"
                status = "online"
            elif time_diff.total_seconds() < 1800:  # 30分以内
                connection_status = "idle"
                status = "offline"
            else:
                connection_status = "offline"
                status = "offline"
        else:
            connection_status = "unknown"
            status = "offline"

        # アクティブ状態を考慮
        if not device.is_active:
            status = "maintenance"

        return DeviceStatus(
            device_id=device.device_id,
            status=status,
            last_seen=device.last_seen,
            connection_status=connection_status,
            last_heartbeat=device.last_seen,
        )

    @staticmethod
    async def get_device_statistics(db: Session, user_id: uuid.UUID = None, broadcast: bool = False) -> dict:
        """デバイス統計情報取得"""
        query = db.query(Device)
        if user_id:
            query = query.filter(Device.owner_id == user_id)

        devices = query.all()
        now = datetime.now(timezone.utc)

        # 基本統計
        total_devices = len(devices)
        online_devices = 0
        offline_devices = 0
        error_devices = 0

        # タイプ別・場所別統計
        by_type = {}
        by_location = {}

        for device in devices:
            # タイプ別
            device_type = device.device_type or "unknown"
            by_type[device_type] = by_type.get(device_type, 0) + 1

            # 場所別
            location = device.location or "未設定"
            by_location[location] = by_location.get(location, 0) + 1

            # 状態判定
            if device.last_seen:
                time_diff = now - device.last_seen
                if time_diff.total_seconds() < 300 and device.is_active:  # 5分以内
                    online_devices += 1
                else:
                    offline_devices += 1
            else:
                offline_devices += 1

        statistics = {
            "total_devices": total_devices,
            "online_devices": online_devices,
            "offline_devices": offline_devices,
            "error_devices": error_devices,
            "by_type": by_type,
            "by_location": by_location,
            "last_updated": now.isoformat(),
            "recent_activity": [],  # 後で実装
        }

        # WebSocketで統計情報をブロードキャスト
        if broadcast:
            await realtime_service.broadcast_device_statistics(statistics)

        return statistics
