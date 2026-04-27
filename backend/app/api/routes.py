from fastapi import APIRouter
from app.api.endpoints import health, csi_data, base_csi, blockchain

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(csi_data.router, prefix="/csi-data", tags=["csi-data"])
api_router.include_router(base_csi.router, prefix="/base-csi", tags=["base-csi"])
api_router.include_router(blockchain.router, prefix="/blockchain", tags=["blockchain"])
