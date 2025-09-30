"""
ヘルスチェック関連エンドポイント
"""

from fastapi import APIRouter
from app.core.config import settings

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
        "environment": "development" if settings.DEBUG else "production"
    }

@router.get("/database")
async def database_health():
    """
    データベース接続チェック
    """
    # TODO: 実際のデータベース接続チェック実装
    return {
        "status": "healthy",
        "database": "postgresql",
        "connected": True
    }

@router.get("/redis")
async def redis_health():
    """
    Redis接続チェック
    """
    # TODO: 実際のRedis接続チェック実装
    return {
        "status": "healthy",
        "cache": "redis",
        "connected": True
    }