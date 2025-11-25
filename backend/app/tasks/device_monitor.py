"""
デバイス監視タスク
定期的にデバイスの状態をチェックし、オフライン状態を検出する
"""

import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import List

from app.core.database import SessionLocal
from app.models.device import Device
from app.services.websocket import RealtimeDataService
from app.services.device import DeviceService

logger = logging.getLogger(__name__)


class DeviceMonitor:
    """デバイス監視クラス"""

    def __init__(self, check_interval: int = 60):
        """
        Args:
            check_interval: チェック間隔（秒）
        """
        self.check_interval = check_interval
        self.running = False

    async def start_monitoring(self):
        """監視開始"""
        if self.running:
            logger.warning("Device monitor is already running")
            return

        self.running = True
        logger.info(f"Starting device monitor with {self.check_interval}s interval")

        try:
            while self.running:
                await self.check_device_status()
                await asyncio.sleep(self.check_interval)
        except Exception as e:
            logger.error(f"Device monitor error: {e}")
        finally:
            self.running = False
            logger.info("Device monitor stopped")

    async def stop_monitoring(self):
        """監視停止"""
        logger.info("Stopping device monitor")
        self.running = False

    async def check_device_status(self):
        """デバイス状態チェック"""
        db = SessionLocal()
        try:
            await self._check_offline_devices(db)
            await self._broadcast_statistics(db)
        except Exception as e:
            logger.error(f"Error checking device status: {e}")
        finally:
            db.close()

    async def _check_offline_devices(self, db: Session):
        """オフラインデバイスをチェック"""
        now = datetime.utcnow()
        offline_threshold = now - timedelta(minutes=5)  # 5分以上応答がない場合オフライン

        # 最近アクティブだったが、現在オフラインと思われるデバイスを取得
        devices = db.query(Device).filter(
            Device.is_active == True,
            Device.last_seen < offline_threshold
        ).all()

        for device in devices:
            # 前回の状態を取得
            previous_status = DeviceService.get_device_status(db, device.device_id)

            # 状態が変更された場合のみ通知
            if previous_status and previous_status.status != "offline":
                await RealtimeDataService.broadcast_device_status({
                    "id": str(device.id),
                    "device_id": device.device_id,
                    "device_name": device.device_name,
                    "device_type": device.device_type,
                    "location": device.location,
                    "status": "offline",
                    "connection_status": "disconnected",
                    "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                    "is_active": device.is_active,
                    "previous_status": previous_status.status
                })

                logger.info(f"Device {device.device_id} went offline")

    async def _broadcast_statistics(self, db: Session):
        """統計情報をブロードキャスト"""
        try:
            statistics = await DeviceService.get_device_statistics(db, broadcast=True)
        except Exception as e:
            logger.error(f"Error broadcasting statistics: {e}")


# グローバルなデバイス監視インスタンス
device_monitor = DeviceMonitor()


async def start_device_monitor():
    """デバイス監視開始（アプリケーション起動時に呼び出される）"""
    await device_monitor.start_monitoring()


async def stop_device_monitor():
    """デバイス監視停止（アプリケーション終了時に呼び出される）"""
    await device_monitor.stop_monitoring()