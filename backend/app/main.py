from pathlib import Path
from typing import Dict
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

_GRAPHS_DIR = Path("/backend/outputs/graphs")
_GRAPHS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/graphs/{csi_data_id}", response_class=Response)
async def graph_gallery(csi_data_id: str) -> Response:
    from fastapi.responses import HTMLResponse
    d = _GRAPHS_DIR / csi_data_id
    base = f"/graphs/{csi_data_id}"

    def _link(filename: str, label: str) -> str:
        path = d / filename
        if not path.exists():
            return ""
        return f'<a href="{base}/{filename}" target="_blank">{label}</a>'

    combined_exists = (d / "combined.png").exists()
    combined_block = ""
    if combined_exists:
        combined_block = f"""
        <section>
          <h2>Combined</h2>
          <div class="dl-links">
            {_link("combined.png", "PNG")}
            {_link("combined.svg", "SVG")}
            {_link("combined.pdf", "PDF")}
          </div>
          <img src="{base}/combined.png" alt="combined">
        </section>
        <hr>
        """

    def _section(title: str, key: str, color: str) -> str:
        if not (d / f"{key}.png").exists():
            return ""
        return f"""
        <section>
          <h2 style="color:{color}">{title}</h2>
          <img src="{base}/{key}.png" alt="{key}">
        </section>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>CSI Spectrum — {csi_data_id}</title>
  <style>
    body {{ font-family: sans-serif; background:#111; color:#eee; margin:0; padding:1rem 2rem; }}
    h1   {{ font-size:1.1rem; color:#aaa; word-break:break-all; }}
    h2   {{ margin-bottom:.4rem; }}
    hr   {{ border-color:#333; margin:2rem 0; }}
    img  {{ max-width:100%; border:1px solid #333; border-radius:4px; margin-top:.5rem; }}
    section {{ margin-bottom:2rem; }}
    .dl-links {{ margin:.4rem 0; }}
    .dl-links a {{
      display:inline-block; margin-right:.8rem; padding:.3rem .8rem;
      background:#2a2a2a; border:1px solid #555; border-radius:4px;
      color:#7cf; text-decoration:none; font-size:.85rem;
    }}
    .dl-links a:hover {{ background:#333; }}
  </style>
</head>
<body>
  <h1>{csi_data_id}</h1>
  <hr>
  {combined_block}
  {_section("FFT", "fft", "#4af")}
  {_section("Wavelet", "wavelet", "#c8f")}
  {_section("MUSIC", "music", "#f88")}
</body>
</html>"""
    return HTMLResponse(content=html)


app.mount("/graphs", StaticFiles(directory=str(_GRAPHS_DIR)), name="graphs")

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
