from typing import Dict
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.errors import setup_error_handlers
from app.api.routes import api_router
from app.services.task_queue import task_queue
from app.services.analysis_tasks import register_task_handlers
from app.services.zkp_service import ZKPService
import logging


def configure_logging() -> None:
    """アプリケーション共通のログ出力を設定"""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root_logger.addHandler(handler)


configure_logging()

# healthチェックのログを除外するフィルタ
class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()

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
    expose_headers=["*"],
)

# APIルーターを登録
app.include_router(api_router, prefix=settings.API_V2_PREFIX)

# エラーハンドラーを登録
setup_error_handlers(app)

logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の初期化処理"""
    try:
        # uvicornのアクセスログからhealthチェックを除外
        logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

        print("⏳ Starting application initialization...")
        logger.info("Starting application initialization...")

        # セキュリティ設定の検証
        _validate_security_settings()
        print("✅ Security settings validated")

        # ZKP回路のセットアップ（必要なら自動コンパイル）
        if settings.ZKP_AUTO_COMPILE:
            print("⏳ Checking ZKP circuits (auto-compile enabled)...")
            try:
                ZKPService(auto_compile=True)
                print("✅ ZKP circuits ready (auto-compile checked)")
            except Exception as e:
                logger.error(f"ZKP circuit setup failed: {e}", exc_info=True)
                print(f"❌ ZKP circuit setup failed: {e}")
                # エラーは継続（開発用途のため）

        # タスクキューに接続
        print("⏳ Connecting to task queue...")
        await task_queue.connect()
        print("✅ Task queue connected")

        # タスクハンドラー登録
        print("⏳ Registering task handlers...")
        register_task_handlers()
        print("✅ Task handlers registered")

        # タスクキューのワーカーを起動
        print("⏳ Starting task workers...")
        await task_queue.start_workers(num_workers=3)
        print("✅ Task workers started")

        logger.info("✅ Application startup completed successfully")
        print("✅ Application startup completed successfully")
    except Exception as e:
        error_msg = f"Failed to initialize application: {e}"
        logger.error(error_msg)
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        raise


def _validate_security_settings():
    """起動時のセキュリティ設定検証"""
    # JWT秘密鍵の検証
    unsafe_secrets = [
        "your-super-secret-jwt-key-change-in-production",
        "secret",
        "changeme",
        "default"
    ]

    if settings.JWT_SECRET_KEY in unsafe_secrets or len(settings.JWT_SECRET_KEY) < 32:
        error_msg = (
            "SECURITY WARNING: JWT_SECRET_KEY is using an unsafe default value or is too short. "
            "Please set a strong JWT_SECRET_KEY (minimum 32 characters) in your environment variables."
        )

        if not settings.DEBUG:
            # 本番環境では起動を拒否
            logger.error(error_msg)
            raise ValueError(error_msg)
        else:
            # 開発環境では警告のみ
            logger.warning(error_msg)


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
