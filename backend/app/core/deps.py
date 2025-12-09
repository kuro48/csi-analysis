"""
FastAPI Dependency関数
"""

import redis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from app.core.database import get_db
from app.core.security import verify_token
from app.core.config import settings
from app.models.user import User
from app.services.cache import  get_analysis_cache, get_session_cache

# OAuth2スキーム設定
security = HTTPBearer()

# Redis クライアント（グローバル）
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Redis クライアントを取得"""
    global _redis_client

    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=False,  # バイナリデータ対応のため
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )

            # 接続テスト
            _redis_client.ping()

        except redis.ConnectionError as e:
            # Redis が利用できない場合はログ出力のみ
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Redis connection failed: {e}. Cache will be disabled.")
            _redis_client = None

    return _redis_client

def get_analysis_cache_service():
    """解析キャッシュサービスを取得"""
    redis_client = get_redis_client()
    if redis_client and settings.CACHE_ENABLED:
        return get_analysis_cache(redis_client)
    return None


def get_session_cache_service():
    """セッションキャッシュサービスを取得"""
    redis_client = get_redis_client()
    if redis_client and settings.CACHE_ENABLED:
        return get_session_cache(redis_client)
    return None


def get_current_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """現在のユーザーを取得（認証必須）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="認証情報が無効です",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # トークンからユーザーIDを取得
        user_id_str = verify_token(credentials.credentials)
        if user_id_str is None:
            raise credentials_exception

        # UUIDに変換
        user_id = uuid.UUID(user_id_str)
    except (ValueError, AttributeError):
        raise credentials_exception

    # データベースからユーザーを取得
    user = db.query(User).filter(
        User.id == user_id,
        User.is_active == True
    ).first()

    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """現在のアクティブユーザーを取得"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="非アクティブユーザーです"
        )
    return current_user


def get_current_superuser(
    current_user: User = Depends(get_current_user)
) -> User:
    """現在のスーパーユーザーを取得"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="スーパーユーザー権限が必要です"
        )
    return current_user