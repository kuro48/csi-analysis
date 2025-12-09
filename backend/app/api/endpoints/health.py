"""
ヘルスチェック関連エンドポイント
"""

import logging

import redis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def health_check():
    """
    システムヘルスチェック
    """
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": "development" if settings.DEBUG else "production",
    }


@router.get("/database")
async def database_health(db: Session = Depends(get_db)):
    """
    データベース接続チェック
    """
    try:
        # データベース接続テスト
        result = db.execute(text("SELECT 1 as test")).fetchone()
        if result and result.test == 1:
            return {
                "status": "healthy",
                "database": "postgresql",
                "connected": True,
                "response_time_ms": 0,  # 実際の測定は省略
            }
        else:
            raise HTTPException(status_code=503, detail="Database connection test failed")
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "database": "postgresql", "connected": False, "error": str(e)},
        )


@router.get("/redis")
async def redis_health():
    """
    Redis接続チェック
    """
    try:
        redis_client = get_redis_client()
        if redis_client is None:
            return {
                "status": "unavailable",
                "cache": "redis",
                "connected": False,
                "message": "Redis is disabled or not configured",
            }

        # Redis接続テスト
        pong = redis_client.ping()
        if pong:
            # 追加の接続テスト
            test_key = "health_check_test"
            redis_client.set(test_key, "test_value", ex=10)
            test_value = redis_client.get(test_key)
            redis_client.delete(test_key)

            return {
                "status": "healthy",
                "cache": "redis",
                "connected": True,
                "ping": True,
                "read_write_test": test_value == b"test_value",
            }
        else:
            raise HTTPException(status_code=503, detail="Redis ping failed")
    except redis.ConnectionError as e:
        logger.error(f"Redis connection failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "cache": "redis",
                "connected": False,
                "error": f"Connection error: {str(e)}",
            },
        )
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        raise HTTPException(
            status_code=503, detail={"status": "unhealthy", "cache": "redis", "connected": False, "error": str(e)}
        )
