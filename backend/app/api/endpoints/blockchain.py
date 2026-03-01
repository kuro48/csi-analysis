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
from app.models.csi_data import CSIData

router = APIRouter()
logger = logging.getLogger(__name__)

# ブロックチェーンサービスのシングルトンインスタンス
blockchain_service = BlockchainService()


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
async def get_blockchain_status() -> Dict[str, Any]:
    """
    ブロックチェーン接続状態を取得

    Returns:
        接続状態とコントラクト情報
    """
    if not blockchain_service.is_available():
        return {
            "connected": False,
            "message": "Blockchain service is not available",
            "rpc_url": blockchain_service.rpc_url,
            "contract_address": blockchain_service.contract_address
        }

    contract_info = blockchain_service.get_contract_info()

    return {
        "connected": True,
        "rpc_url": blockchain_service.rpc_url,
        "contract_address": blockchain_service.contract_address,
        "chain_id": blockchain_service.w3.eth.chain_id,
        "current_block": blockchain_service.w3.eth.block_number,
        "contract_info": contract_info
    }


@router.get("/proof/{proof_id}")
async def get_zkp_proof_by_id(
    proof_id: str
) -> Dict[str, Any]:
    """
    証明IDからZKP証明を取得

    Args:
        proof_id: 証明ID（hex文字列）

    Returns:
        証明レコード
    """
    if not blockchain_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Blockchain service is not available"
        )

    try:
        proof_record = blockchain_service.get_zkp_proof_by_id(proof_id)

        if not proof_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proof not found on blockchain"
            )

        return proof_record

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get proof: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get proof: {str(e)}"
        )


@router.get("/device/{device_id}/proofs")
async def get_device_proofs(
    device_id: str
) -> Dict[str, Any]:
    """
    デバイスIDから証明IDリストを取得

    Args:
        device_id: デバイスID

    Returns:
        証明IDリスト
    """
    if not blockchain_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Blockchain service is not available"
        )

    try:
        proof_ids = blockchain_service.get_device_proof_ids(device_id)

        return {
            "device_id": device_id,
            "proof_count": len(proof_ids),
            "proof_ids": proof_ids
        }

    except Exception as e:
        logger.error(f"Failed to get device proofs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get device proofs: {str(e)}"
        )


@router.get("/device/{device_id}/latest-proof")
async def get_latest_device_proof(
    device_id: str
) -> Dict[str, Any]:
    """
    デバイスの最新のZKP証明を取得

    Args:
        device_id: デバイスID

    Returns:
        最新の証明レコード
    """
    if not blockchain_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Blockchain service is not available"
        )

    try:
        proof_record = blockchain_service.get_latest_device_proof(device_id)

        if not proof_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No proofs found for this device"
            )

        return proof_record

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get latest device proof: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get latest device proof: {str(e)}"
        )


@router.post("/verify-proof-on-chain")
async def verify_proof_on_chain(
    request: VerifyProofOnChainRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    ZKP証明をオンチェーンで検証して結果を記録。

    proof / public_signals を省略した場合は DB から自動取得するため、
    proof_id だけで任意タイミングに呼び出せる。

    Args:
        request: 検証リクエスト（proof_id 必須、proof/public_signals は省略可）

    Returns:
        検証結果
    """
    if not blockchain_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Blockchain service is not available"
        )

    if not blockchain_service.is_verifier_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verifier contract is not available"
        )

    proof = request.proof
    public_signals = request.public_signals

    # proof/public_signals が渡されなかった場合は DB から取得
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
        if proof is None:
            proof = stored.get("proof")
        if public_signals is None:
            public_signals = stored.get("public_signals")

    try:
        is_valid = blockchain_service.verify_and_mark_proof(
            proof_id=request.proof_id,
            proof=proof,
            public_signals=public_signals,
        )

        if is_valid is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Verification could not be completed (proof data format invalid)"
            )

        return {
            "success": True,
            "proof_id": request.proof_id,
            "is_valid": is_valid,
            "message": f"Proof verified on chain: {'valid' if is_valid else 'invalid'}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to verify proof on chain: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify proof on chain: {str(e)}"
        )
