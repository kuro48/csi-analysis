"""
WebSocket リアルタイム通信エンドポイント
"""

from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.routing import APIRouter
import json
import uuid
from typing import Optional
import asyncio

from app.services.websocket import manager, RealtimeDataService
from app.core.security import verify_token
from app.core.database import get_db
from app.models.user import User

router = APIRouter()


async def send_ping_periodically(websocket: WebSocket, connection_id: str):
    """定期的にPingを送信して接続を維持"""
    try:
        while True:
            await asyncio.sleep(40)  # 40秒ごとに変更して負荷を軽減
            try:
                await websocket.ping()
            except Exception:
                # Ping送信に失敗した場合は終了
                break
    except asyncio.CancelledError:
        pass


async def get_current_user_websocket(websocket: WebSocket) -> Optional[User]:
    """WebSocket接続での認証チェック"""
    try:
        # クエリパラメータからトークンを取得
        token = websocket.query_params.get("token")
        if not token:
            return None

        # トークンを検証
        user_id_str = verify_token(token)
        if not user_id_str:
            return None

        # データベースからユーザーを取得（簡略化版）
        # 実際の実装ではget_dbを使用
        return User(id=uuid.UUID(user_id_str), username="authenticated_user")

    except Exception:
        return None


@router.websocket("/realtime")
async def websocket_endpoint(websocket: WebSocket):
    """
    リアルタイム通信エンドポイント

    接続URL例: ws://localhost:8000/api/v2/ws/realtime?token=YOUR_JWT_TOKEN
    """
    connection_id = str(uuid.uuid4())
    user = None

    try:
        # 認証チェック（オプション）
        user = await get_current_user_websocket(websocket)
        user_id = str(user.id) if user else None

        # 接続を受け入れ（認証失敗でも接続を許可）
        await websocket.accept()
        await manager.connect(websocket, connection_id, user_id)

        # 接続成功メッセージを送信
        welcome_message = {
            "type": "connection_established",
            "connection_id": connection_id,
            "authenticated": user is not None,
            "timestamp": "2024-12-01T00:00:00"  # 実際は datetime.utcnow().isoformat()
        }
        await manager.send_personal_message(welcome_message, connection_id)

        # 定期的にPingを送信するタスクを開始
        ping_task = asyncio.create_task(send_ping_periodically(websocket, connection_id))

        # メッセージ処理ループ
        try:
            while True:
                try:
                    # タイムアウト付きでメッセージを受信（60秒）
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                    message = json.loads(data)

                    await handle_websocket_message(connection_id, message, user_id)

                except asyncio.TimeoutError:
                    # タイムアウトの場合は続行（Pingタスクがあるのでここでは何もしない）
                    continue
                except WebSocketDisconnect:
                    break
                except json.JSONDecodeError:
                    # 無効なJSONの場合はエラーメッセージを送信
                    error_message = {
                        "type": "error",
                        "message": "Invalid JSON format"
                    }
                    await manager.send_personal_message(error_message, connection_id)
                except Exception as e:
                    # その他のエラー
                    error_message = {
                        "type": "error",
                        "message": f"Server error: {str(e)}"
                    }
                    await manager.send_personal_message(error_message, connection_id)
        finally:
            # Pingタスクをキャンセル
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # 接続を削除
        manager.disconnect(connection_id, user_id)


async def handle_websocket_message(connection_id: str, message: dict, user_id: str = None):
    """WebSocketメッセージの処理"""
    message_type = message.get("type")

    if message_type == "subscribe":
        # チャンネル購読
        channel = message.get("channel")
        if channel:
            await manager.subscribe_to_channel(connection_id, channel)
            response = {
                "type": "subscribed",
                "channel": channel,
                "message": f"Successfully subscribed to {channel}"
            }
            await manager.send_personal_message(response, connection_id)

    elif message_type == "unsubscribe":
        # チャンネル購読解除
        channel = message.get("channel")
        if channel:
            await manager.unsubscribe_from_channel(connection_id, channel)
            response = {
                "type": "unsubscribed",
                "channel": channel,
                "message": f"Successfully unsubscribed from {channel}"
            }
            await manager.send_personal_message(response, connection_id)

    elif message_type == "ping":
        # ヘルスチェック
        response = {
            "type": "pong",
            "timestamp": "2024-12-01T00:00:00"  # 実際は datetime.utcnow().isoformat()
        }
        await manager.send_personal_message(response, connection_id)

    elif message_type == "get_status":
        # 接続状態取得
        response = {
            "type": "status",
            "connection_id": connection_id,
            "authenticated": user_id is not None,
            "active_connections": manager.get_connection_count()
        }
        await manager.send_personal_message(response, connection_id)

    else:
        # 未知のメッセージタイプ
        response = {
            "type": "error",
            "message": f"Unknown message type: {message_type}"
        }
        await manager.send_personal_message(response, connection_id)


# テスト用エンドポイント（開発時のみ使用）
@router.post("/test/broadcast")
async def test_broadcast(message: dict):
    """
    テスト用ブロードキャストエンドポイント
    開発・デバッグ時のみ使用
    """
    await manager.broadcast_to_all({
        "type": "test_message",
        "data": message,
        "timestamp": "2024-12-01T00:00:00"
    })
    return {"message": "Test broadcast sent"}


@router.post("/test/channel-broadcast")
async def test_channel_broadcast(channel: str, message: dict):
    """
    テスト用チャンネルブロードキャストエンドポイント
    """
    await manager.broadcast_to_channel({
        "type": "test_channel_message",
        "channel": channel,
        "data": message,
        "timestamp": "2024-12-01T00:00:00"
    }, channel)
    return {"message": f"Test broadcast sent to channel: {channel}"}


@router.get("/stats")
async def get_websocket_stats():
    """
    WebSocket接続統計情報を取得
    """
    return {
        "active_connections": manager.get_connection_count(),
        "channels": {
            channel: manager.get_channel_subscriber_count(channel)
            for channel in manager.channel_subscribers.keys()
        }
    }