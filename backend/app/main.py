from typing import Dict
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.core.errors import setup_error_handlers
from app.api.routes import api_router
from app.services.zkp_service import ZKPService
import logging


def configure_logging() -> None:
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


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V2_PREFIX}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not settings.DEBUG:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.include_router(api_router, prefix=settings.API_V2_PREFIX)
setup_error_handlers(app)

logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_event():
    try:
        logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

        print("⏳ Starting application initialization...")
        logger.info("Starting application initialization...")

        _validate_security_settings()
        print("✅ Security settings validated")

        if settings.ZKP_AUTO_COMPILE:
            print("⏳ Checking ZKP circuits (auto-compile enabled)...")
            try:
                ZKPService(auto_compile=True)
                print("✅ ZKP circuits ready (auto-compile checked)")
            except Exception as e:
                logger.error(f"ZKP circuit setup failed: {e}", exc_info=True)
                print(f"❌ ZKP circuit setup failed: {e}")

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
    """JWT_SECRET_KEYが安全なデフォルト値でないことを確認する。本番環境では起動を拒否する。"""
    unsafe_secrets = [
        "your-super-secret-jwt-key-change-in-production",
        "secret",
        "changeme",
        "default",
    ]
    if settings.JWT_SECRET_KEY in unsafe_secrets or len(settings.JWT_SECRET_KEY) < 32:
        error_msg = (
            "SECURITY WARNING: JWT_SECRET_KEY is using an unsafe default value or is too short. "
            "Please set a strong JWT_SECRET_KEY (minimum 32 characters) in your environment variables."
        )
        if not settings.DEBUG:
            logger.error(error_msg)
            raise ValueError(error_msg)
        else:
            logger.warning(error_msg)


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown completed successfully")


@app.get("/")
async def root() -> Dict[str, str]:
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "api_prefix": settings.API_V2_PREFIX,
    }


@app.get("/health")
async def health_check() -> Dict[str, str]:
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
