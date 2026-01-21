"""
ブロックチェーン連携エンドポイント

ZKP証明をブロックチェーンに記録・取得するためのエンドポイント
"""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import logging

from app.services.blockchain_service import BlockchainService

router = APIRouter()
logger = logging.getLogger(__name__)

# ブロックチェーンサービスのシングルトンインスタンス
blockchain_service = BlockchainService()


class VerifyProofOnChainRequest(BaseModel):
    """証明検証リクエスト"""
    proof_id: str


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
    request: VerifyProofOnChainRequest
) -> Dict[str, Any]:
    """
    ZKP証明をオンチェーンで検証して結果を記録

    Args:
        request: 検証リクエスト

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

    try:
        is_valid = blockchain_service.verify_and_mark_proof(request.proof_id)

        if is_valid is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify proof on blockchain"
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
