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
    """WebSocket接続での認証チェック（強化版）"""
    try:
        # クエリパラメータからトークンを取得
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4001, reason="Authentication token required")
            return None

        # トークンを検証
        try:
            user_id_str = verify_token(token)
            if not user_id_str:
                await websocket.close(code=4001, reason="Invalid or expired token")
                return None
        except Exception as e:
            await websocket.close(code=4001, reason=f"Token verification failed: {str(e)}")
            return None

        # データベースからユーザーを取得（実際の実装）
        try:
            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.id == uuid.UUID(user_id_str)).first()
                if not user or not user.is_active:
                    await websocket.close(code=4003, reason="User not found or inactive")
                    return None
                return user
            finally:
                db.close()
        except Exception as e:
            await websocket.close(code=4002, reason=f"Database error: {str(e)}")
            return None

    except Exception as e:
        await websocket.close(code=4000, reason=f"Authentication error: {str(e)}")
        return None


def is_channel_accessible(channel: str, user: User) -> bool:
    """チャンネルアクセス権限チェック"""
    if not user:
        return False

    # チャンネル別アクセス制御
    if channel.startswith("admin_"):
        # 管理者専用チャンネル
        return user.role in ["superuser", "admin"]
    elif channel.startswith("device_"):
        # デバイス関連チャンネル（デバイス所有者のみ）
        device_id = channel.replace("device_", "")
        # 実際の実装では、デバイス所有権をチェック
        # 簡略化版では全ユーザーに許可
        return True
    elif channel.startswith("system_"):
        # システム関連チャンネル（管理者のみ）
        return user.role in ["superuser", "admin"]
    elif channel in ["general", "notifications"]:
        # 一般チャンネル（全ユーザー）
        return True
    else:
        # その他のチャンネル（一般ユーザーに許可）
        return True


@router.websocket("/realtime")
async def websocket_endpoint(websocket: WebSocket):
    """
    リアルタイム通信エンドポイント

    接続URL例: ws://localhost:8000/api/v2/ws/realtime?token=YOUR_JWT_TOKEN
    """
    connection_id = str(uuid.uuid4())
    user = None

    try:
        # 認証チェック（必須）
        user = await get_current_user_websocket(websocket)
        if not user:
            # 認証失敗の場合は接続を拒否（get_current_user_websocketで既にcloseされている）
            return

        user_id = str(user.id)

        # 認証成功後に接続を受け入れ
        await websocket.accept()
        await manager.connect(websocket, connection_id, user_id)

        # 接続成功メッセージを送信
        welcome_message = {
            "type": "connection_established",
            "connection_id": connection_id,
            "authenticated": True,
            "user": {
                "id": str(user.id),
                "username": user.username,
                "role": user.role
            },
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

                    await handle_websocket_message(connection_id, message, user)

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
        logger.error(f"WebSocket error: {e}")
    finally:
        # 接続を削除
        manager.disconnect(connection_id, str(user.id) if user else None)


async def handle_websocket_message(connection_id: str, message: dict, user: User = None):
    """WebSocketメッセージの処理（ロール基盤アクセス制御付き）"""
    message_type = message.get("type")

    if message_type == "subscribe":
        # チャンネル購読（ロール確認付き）
        channel = message.get("channel")
        if channel and is_channel_accessible(channel, user):
            await manager.subscribe_to_channel(connection_id, channel)
            response = {
                "type": "subscribed",
                "channel": channel,
                "message": f"Successfully subscribed to {channel}"
            }
            await manager.send_personal_message(response, connection_id)
        else:
            response = {
                "type": "error",
                "message": f"Access denied to channel: {channel}"
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
            "authenticated": user is not None,
            "user_role": user.role if user else None,
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