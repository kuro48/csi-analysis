"""
ブロックチェーン連携エンドポイント

ZKP証明をブロックチェーンに記録・取得するためのエンドポイント
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging

from app.services.blockchain_service import BlockchainService
from app.core.database import get_db
from app.core.config import settings
from app.models.csi_data import CSIData

router = APIRouter()
logger = logging.getLogger(__name__)

# 遅延初期化シングルトン（FastAPI Depends 経由で注入）
_blockchain_service_instance: Optional[BlockchainService] = None


def get_blockchain_service() -> BlockchainService:
    """BlockchainService の遅延初期化シングルトンを返す依存性プロバイダー"""
    global _blockchain_service_instance
    if _blockchain_service_instance is None:
        _blockchain_service_instance = BlockchainService(
            rpc_url=settings.ETHEREUM_RPC_URL,
            contract_address=settings.ZKPROOF_CONTRACT_ADDRESS,
            account_private_key=settings.BLOCKCHAIN_PRIVATE_KEY or None,
        )
    return _blockchain_service_instance


class VerifyProofOnChainRequest(BaseModel):
    """証明検証リクエスト"""
    proof_id: str
    proof: Optional[Dict[str, Any]] = None          # 直接渡す場合（省略時はDBから取得）
    public_signals: Optional[List[Any]] = None       # 直接渡す場合（省略時はDBから取得）


def _lookup_proof_data_from_db(
    proof_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """
    proof_id に対応する証明データを DB の processed_data から取得する。
    記録時に保存した blockchain_proof_data キーを参照する。
    """
    row = (
        db.query(CSIData)
        .filter(
            CSIData.processed_data["blockchain_proof_id"].astext == proof_id
        )
        .first()
    )
    if row is None:
        return None
    return (row.processed_data or {}).get("blockchain_proof_data")


# ===== エンドポイント =====

@router.get("/status")
async def get_blockchain_status(
    service: BlockchainService = Depends(get_blockchain_service),
) -> Dict[str, Any]:
    """ブロックチェーン接続状態を取得"""
    if not service.is_available():
        return {
            "connected": False,
            "message": "Blockchain service is not available",
            "rpc_url": service.rpc_url,
            "contract_address": service.contract_address,
        }

    contract_info = service.get_contract_info()
    return {
        "connected": True,
        "rpc_url": service.rpc_url,
        "contract_address": service.contract_address,
        "chain_id": service.w3.eth.chain_id,
        "current_block": service.w3.eth.block_number,
        "contract_info": contract_info,
    }


@router.get("/proof/{proof_id}")
async def get_zkp_proof_by_id(
    proof_id: str,
    service: BlockchainService = Depends(get_blockchain_service),
) -> Dict[str, Any]:
    """証明IDからZKP証明を取得"""
    if not service.is_available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Blockchain service is not available")
    try:
        proof_record = service.get_zkp_proof_by_id(proof_id)
        if not proof_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Proof not found on blockchain")
        return proof_record
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get proof {proof_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to retrieve proof")


@router.get("/device/{device_id}/proofs")
async def get_device_proofs(
    device_id: str,
    service: BlockchainService = Depends(get_blockchain_service),
) -> Dict[str, Any]:
    """デバイスIDから証明IDリストを取得"""
    if not service.is_available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Blockchain service is not available")
    try:
        proof_ids = service.get_device_proof_ids(device_id)
        return {"device_id": device_id, "proof_count": len(proof_ids), "proof_ids": proof_ids}
    except Exception as e:
        logger.error(f"Failed to get proofs for device {device_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to retrieve device proofs")


@router.get("/device/{device_id}/latest-proof")
async def get_latest_device_proof(
    device_id: str,
    service: BlockchainService = Depends(get_blockchain_service),
) -> Dict[str, Any]:
    """デバイスの最新のZKP証明を取得"""
    if not service.is_available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Blockchain service is not available")
    try:
        proof_record = service.get_latest_device_proof(device_id)
        if not proof_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="No proofs found for this device")
        return proof_record
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get latest proof for device {device_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to retrieve latest device proof")


@router.post("/verify-proof-on-chain")
async def verify_proof_on_chain(
    request: VerifyProofOnChainRequest,
    db: Session = Depends(get_db),
    service: BlockchainService = Depends(get_blockchain_service),
) -> Dict[str, Any]:
    """
    ZKP証明をオンチェーンで検証して結果を記録。

    proof / public_signals を省略した場合は DB から自動取得するため、
    proof_id だけで任意タイミングに呼び出せる。
    """
    if not service.is_available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Blockchain service is not available")
    if not service.is_verifier_available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Verifier contract is not available")

    proof = request.proof
    public_signals = request.public_signals

    if proof is None or public_signals is None:
        stored = _lookup_proof_data_from_db(request.proof_id, db)
        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Proof data not found in DB for this proof_id. "
                    "Pass 'proof' and 'public_signals' explicitly, or re-upload the CSI data."
                ),
            )
        proof = proof or stored.get("proof")
        public_signals = public_signals or stored.get("public_signals")

    try:
        is_valid = service.verify_and_mark_proof(
            proof_id=request.proof_id,
            proof=proof,
            public_signals=public_signals,
        )
        if is_valid is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Verification could not be completed (proof data format invalid)",
            )
        return {
            "success": True,
            "proof_id": request.proof_id,
            "is_valid": is_valid,
            "message": f"Proof verified on chain: {'valid' if is_valid else 'invalid'}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to verify proof {request.proof_id} on chain: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to verify proof on chain")
