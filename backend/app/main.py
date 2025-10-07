from typing import Dict
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import api_router
from app.services.task_queue import task_queue
from app.services.analysis_tasks import register_task_handlers
import logging

# アプリケーション初期化
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V2_PREFIX}/openapi.json",
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# APIルーターを登録
app.include_router(api_router, prefix=settings.API_V2_PREFIX)

logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の初期化処理"""
    try:
        # タスクキューに接続
        await task_queue.connect()

        # タスクハンドラー登録
        register_task_handlers()

        logger.info("Application startup completed successfully")
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時のクリーンアップ処理"""
    try:
        # ワーカー停止
        await task_queue.stop_workers()

        # タスクキューから切断
        await task_queue.disconnect()

        logger.info("Application shutdown completed successfully")
    except Exception as e:
        logger.error(f"Error during application shutdown: {e}")


@app.get("/")
async def root() -> Dict[str, str]:
    """ルートエンドポイント"""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "api_prefix": settings.API_V2_PREFIX
    }


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """基本ヘルスチェックエンドポイント（後方互換性）"""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )