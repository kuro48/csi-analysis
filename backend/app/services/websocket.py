"""
WebSocket接続管理とリアルタイムデータサービス
"""

from typing import Dict, List, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class WebSocketConnection:
    """単一のWebSocket接続を管理"""

    def __init__(self, websocket: WebSocket, connection_id: str, user_id: Optional[str] = None):
        self.websocket = websocket
        self.connection_id = connection_id
        self.user_id = user_id
        self.channels: set = set()
        self.created_at = datetime.utcnow()

    async def send_message(self, message: dict):
        """メッセージを送信"""
        try:
            await self.websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {self.connection_id}: {e}")
            return False


class WebSocketManager:
    """WebSocket接続の管理"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocketConnection] = {}
        self.channel_subscribers: Dict[str, set] = {}

    async def connect(self, websocket: WebSocket, connection_id: str, user_id: Optional[str] = None):
        """新しい接続を追加"""
        connection = WebSocketConnection(websocket, connection_id, user_id)
        self.active_connections[connection_id] = connection
        logger.info(f"WebSocket connected: {connection_id}, user: {user_id}")

    def disconnect(self, connection_id: str, user_id: Optional[str] = None):
        """接続を削除"""
        if connection_id in self.active_connections:
            connection = self.active_connections[connection_id]

            # すべてのチャンネルから購読を解除
            for channel in connection.channels.copy():
                self.unsubscribe_from_channel_sync(connection_id, channel)

            # 接続を削除
            del self.active_connections[connection_id]
            logger.info(f"WebSocket disconnected: {connection_id}, user: {user_id}")

    async def send_personal_message(self, message: dict, connection_id: str):
        """特定の接続にメッセージを送信"""
        if connection_id in self.active_connections:
            connection = self.active_connections[connection_id]
            success = await connection.send_message(message)
            if not success:
                # 送信に失敗した場合は接続を削除
                self.disconnect(connection_id, connection.user_id)

    async def broadcast_to_all(self, message: dict):
        """すべての接続にブロードキャスト"""
        if not self.active_connections:
            return

        failed_connections = []
        tasks = []
        connections = list(self.active_connections.values())

        for connection in connections:
            tasks.append(connection.send_message(message))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 失敗した接続を収集
            for i, result in enumerate(results):
                if result is False or isinstance(result, Exception):
                    failed_connections.append(connections[i])

            # 失敗した接続を削除
            for connection in failed_connections:
                self.disconnect(connection.connection_id, connection.user_id)

    async def broadcast_to_channel(self, message: dict, channel: str):
        """特定のチャンネルにブロードキャスト"""
        if channel not in self.channel_subscribers:
            return

        failed_connections = []
        tasks = []
        connections = []

        for connection_id in self.channel_subscribers[channel]:
            if connection_id in self.active_connections:
                connection = self.active_connections[connection_id]
                connections.append(connection)
                tasks.append(connection.send_message(message))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 失敗した接続を収集
            for i, result in enumerate(results):
                if result is False or isinstance(result, Exception):
                    failed_connections.append(connections[i])

            # 失敗した接続を削除
            for connection in failed_connections:
                self.disconnect(connection.connection_id, connection.user_id)

    async def subscribe_to_channel(self, connection_id: str, channel: str):
        """チャンネルに購読"""
        if connection_id in self.active_connections:
            connection = self.active_connections[connection_id]
            connection.channels.add(channel)

            if channel not in self.channel_subscribers:
                self.channel_subscribers[channel] = set()
            self.channel_subscribers[channel].add(connection_id)

            logger.info(f"Connection {connection_id} subscribed to channel: {channel}")

    async def unsubscribe_from_channel(self, connection_id: str, channel: str):
        """チャンネルから購読解除"""
        self.unsubscribe_from_channel_sync(connection_id, channel)

    def unsubscribe_from_channel_sync(self, connection_id: str, channel: str):
        """チャンネルから購読解除（同期版）"""
        if connection_id in self.active_connections:
            connection = self.active_connections[connection_id]
            connection.channels.discard(channel)

        if channel in self.channel_subscribers:
            self.channel_subscribers[channel].discard(connection_id)

            # チャンネルに購読者がいなくなった場合は削除
            if not self.channel_subscribers[channel]:
                del self.channel_subscribers[channel]

        logger.info(f"Connection {connection_id} unsubscribed from channel: {channel}")

    def get_connection_count(self) -> int:
        """アクティブな接続数を取得"""
        return len(self.active_connections)

    def get_channel_subscriber_count(self, channel: str) -> int:
        """特定のチャンネルの購読者数を取得"""
        return len(self.channel_subscribers.get(channel, set()))


class RealtimeDataService:
    """リアルタイムデータサービス"""

    def __init__(self, websocket_manager: WebSocketManager):
        self.manager = websocket_manager

    async def broadcast_device_status_update(self, device_id: str, status_data: dict):
        """デバイス状態更新をブロードキャスト"""
        message = {
            "type": "device_status_update",
            "device_id": device_id,
            "data": status_data,
            "timestamp": datetime.utcnow().isoformat()
        }

        # デバイス固有のチャンネルとダッシュボードチャンネルにブロードキャスト
        await self.manager.broadcast_to_channel(message, f"device_{device_id}")
        await self.manager.broadcast_to_channel(message, "dashboard")

    async def broadcast_breathing_analysis_update(self, device_id: str, analysis_data: dict):
        """呼吸解析結果更新をブロードキャスト"""
        message = {
            "type": "breathing_analysis_update",
            "device_id": device_id,
            "data": analysis_data,
            "timestamp": datetime.utcnow().isoformat()
        }

        # デバイス固有のチャンネルとダッシュボードチャンネルにブロードキャスト
        await self.manager.broadcast_to_channel(message, f"device_{device_id}")
        await self.manager.broadcast_to_channel(message, "dashboard")

    async def broadcast_system_notification(self, notification_data: dict):
        """システム通知をブロードキャスト"""
        message = {
            "type": "system_notification",
            "data": notification_data,
            "timestamp": datetime.utcnow().isoformat()
        }

        # 全接続にブロードキャスト
        await self.manager.broadcast_to_all(message)


# グローバルインスタンス
manager = WebSocketManager()
realtime_service = RealtimeDataService(manager)