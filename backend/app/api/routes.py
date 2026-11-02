from fastapi import APIRouter, Depends
from app.api.endpoints import health, csi_data, base_csi, blockchain, breathing, onchain
from app.core.access import require_operator

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(onchain.router, prefix="/onchain", tags=["onchain"])
api_router.include_router(breathing.router, prefix="/breathing", tags=["breathing"], dependencies=[Depends(require_operator)])
api_router.include_router(csi_data.router, prefix="/csi-data", tags=["csi-data"], dependencies=[Depends(require_operator)])
api_router.include_router(base_csi.router, prefix="/base-csi", tags=["base-csi"], dependencies=[Depends(require_operator)])
api_router.include_router(blockchain.router, prefix="/blockchain", tags=["blockchain"], dependencies=[Depends(require_operator)])
