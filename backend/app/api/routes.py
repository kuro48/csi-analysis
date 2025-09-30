"""
APIルーター統合モジュール
"""

from fastapi import APIRouter
from app.api.endpoints import health, auth, devices, csi_data, breathing_analysis, websocket

api_router = APIRouter()

# 各エンドポイントをルーターに登録
api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"]
)

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["authentication"]
)

api_router.include_router(
    devices.router,
    prefix="/devices",
    tags=["devices"]
)

api_router.include_router(
    csi_data.router,
    prefix="/csi-data",
    tags=["csi-data"]
)

api_router.include_router(
    breathing_analysis.router,
    prefix="/breathing-analysis",
    tags=["breathing-analysis"]
)

api_router.include_router(
    websocket.router,
    prefix="/ws",
    tags=["websocket"]
)