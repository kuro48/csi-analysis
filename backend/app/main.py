import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings, validate_security_settings as _check_required_env_vars
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
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


configure_logging()


class HealthCheckFilter(logging.Filter):
    _SKIP = ("/health", '"GET /api/v2/csi-data/', '"GET /api/v2/base-csi/')

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(s in msg for s in self._SKIP)


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
app.state.config = settings

_GRAPHS_DIR = Path(os.environ.get("GRAPH_OUTPUT_DIR", "/app/outputs/graphs"))
try:
    _GRAPHS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Docker外（ローカル開発・テスト）では /app を作成できないため一時領域へ退避
    _GRAPHS_DIR = Path(tempfile.gettempdir()) / "csi_graphs"
    _GRAPHS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/graphs", response_class=Response)
async def graph_index() -> Response:
    from fastapi.responses import HTMLResponse
    import datetime

    entries = []
    for d in _GRAPHS_DIR.iterdir():
        if not d.is_dir():
            continue
        mtime = d.stat().st_mtime
        dt = datetime.datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone()
        has = {
            "combined": (d / "combined.png").exists(),
            "fft":      (d / "fft.png").exists(),
            "wavelet":  (d / "wavelet.png").exists(),
            "music":    (d / "music.png").exists(),
        }
        entries.append((dt, d.name, has))

    entries.sort(key=lambda x: x[0], reverse=True)

    def _badge(label: str, color: str, active: bool) -> str:
        if not active:
            return f'<span class="badge off">{label}</span>'
        return f'<span class="badge" style="background:{color}">{label}</span>'

    rows = ""
    for dt, csi_id, has in entries:
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M:%S")
        badges = (
            _badge("combined", "#555", has["combined"])
            + _badge("FFT",      "#4af", has["fft"])
            + _badge("Wavelet",  "#c8f", has["wavelet"])
            + _badge("MUSIC",    "#f88", has["music"])
        )
        thumb = f'<img class="thumb" src="/graphs/{csi_id}/combined.png" alt="">' if has["combined"] else \
                f'<img class="thumb" src="/graphs/{csi_id}/fft.png" alt="">'     if has["fft"] else \
                '<div class="thumb no-img">no image</div>'
        rows += f"""
        <tr onclick="location.href='/graphs/{csi_id}'">
          <td class="td-thumb">{thumb}</td>
          <td class="td-date"><span class="date">{date_str}</span><br><span class="time">{time_str}</span></td>
          <td class="td-id"><code>{csi_id}</code></td>
          <td class="td-badges">{badges}</td>
        </tr>"""

    empty_msg = "" if entries else '<p style="color:#666;text-align:center;padding:3rem">グラフがまだありません</p>'

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>CSI Graph Index</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body   {{ font-family: sans-serif; background:#111; color:#eee; margin:0; padding:1.5rem 2rem; }}
    h1     {{ font-size:1.2rem; color:#aaa; margin-bottom:1.2rem; }}
    table  {{ width:100%; border-collapse:collapse; }}
    th     {{ text-align:left; padding:.5rem .8rem; border-bottom:1px solid #333; color:#888; font-weight:normal; font-size:.8rem; text-transform:uppercase; letter-spacing:.06em; }}
    tr[onclick] {{ cursor:pointer; }}
    tr[onclick]:hover td {{ background:#1a1a1a; }}
    td     {{ padding:.55rem .8rem; border-bottom:1px solid #222; vertical-align:middle; }}
    .td-thumb  {{ width:140px; }}
    .td-date   {{ width:110px; white-space:nowrap; }}
    .td-id     {{ font-size:.82rem; word-break:break-all; }}
    .td-badges {{ width:220px; }}
    .date  {{ color:#ccc; font-size:.9rem; }}
    .time  {{ color:#888; font-size:.8rem; }}
    code   {{ color:#7cf; background:#1e1e2e; padding:.15rem .4rem; border-radius:3px; font-size:.78rem; }}
    .thumb {{ width:130px; height:60px; object-fit:cover; border-radius:4px; border:1px solid #333; display:block; }}
    .no-img {{ width:130px; height:60px; border-radius:4px; border:1px solid #333; display:flex; align-items:center; justify-content:center; color:#555; font-size:.75rem; background:#1a1a1a; }}
    .badge {{ display:inline-block; font-size:.72rem; padding:.15rem .5rem; border-radius:3px; margin:.15rem .15rem 0 0; color:#fff; }}
    .badge.off {{ background:#2a2a2a; color:#555; }}
    .count {{ color:#888; font-size:.85rem; margin-bottom:.8rem; }}
  </style>
</head>
<body>
  <h1>CSI Graph Index</h1>
  <p class="count">{len(entries)} 件</p>
  {empty_msg}
  {'<table><thead><tr><th></th><th>日時</th><th>CSI Data ID</th><th>グラフ</th></tr></thead><tbody>' + rows + '</tbody></table>' if entries else ''}
</body>
</html>"""
    return HTMLResponse(content=html)


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
    h1   {{ font-size:1.1rem; color:#aaa; word-break:break-all; margin-top:.5rem; }}
    h2   {{ margin-bottom:.4rem; }}
    hr   {{ border-color:#333; margin:2rem 0; }}
    img  {{ max-width:100%; border:1px solid #333; border-radius:4px; margin-top:.5rem; }}
    section {{ margin-bottom:2rem; }}
    .dl-links {{ margin:.4rem 0; }}
    .dl-links a, .back {{
      display:inline-block; margin-right:.8rem; padding:.3rem .8rem;
      background:#2a2a2a; border:1px solid #555; border-radius:4px;
      color:#7cf; text-decoration:none; font-size:.85rem;
    }}
    .dl-links a:hover, .back:hover {{ background:#333; }}
    .back {{ margin-bottom:.5rem; }}
  </style>
</head>
<body>
  <a class="back" href="/graphs">← 一覧へ</a>
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

        logger.info("Starting application initialization...")

        _check_required_env_vars()   # 必須環境変数の存在チェック（config.py）
        _validate_security_settings()  # JWT_SECRET_KEY の強度チェック
        logger.info("Security settings validated")

        if settings.ZKP_AUTO_COMPILE:
            logger.info("Checking ZKP circuits (auto-compile enabled)...")
            try:
                ZKPService(auto_compile=True)
                logger.info("ZKP circuits ready (auto-compile checked)")
            except Exception as e:
                logger.error(f"ZKP circuit setup failed: {e}", exc_info=True)

        logger.info("Application startup completed successfully")
    except Exception as e:
        error_msg = f"Failed to initialize application: {e}"
        logger.error(error_msg)
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
