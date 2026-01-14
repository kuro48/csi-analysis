"""
ブロックチェーン連携エンドポイント

ZKP証明をブロックチェーンに記録・取得するためのエンドポイント
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from uuid import UUID
import logging

from app.core.database import get_db
from app.models.csi_data import CSIData
from app.services.blockchain_service import BlockchainService

router = APIRouter()
logger = logging.getLogger(__name__)

# ブロックチェーンサービスのシングルトンインスタンス
blockchain_service = BlockchainService()


# ===== Pydanticスキーマ =====

class RecordProofRequest(BaseModel):
    """ZKP証明記録リクエスト"""
    device_id: str
    proof: Dict[str, Any]
    public_signals: List[Any]
    proof_type: str = "full_similarity"
    data_hash: Optional[str] = None


class RecordProofFromCSIRequest(BaseModel):
    """CSIデータからZKP証明記録リクエスト"""
    csi_data_id: UUID
    proof_type: str = "full_similarity"


class VerifyProofOnChainRequest(BaseModel):
    """証明検証リクエスト"""
    proof_id: str
    is_valid: bool


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


@router.post("/record-proof")
async def record_zkp_proof(
    request: RecordProofRequest
) -> Dict[str, Any]:
    """
    ZKP証明をブロックチェーンに記録

    Args:
        request: 証明記録リクエスト

    Returns:
        記録結果
    """
    if not blockchain_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Blockchain service is not available"
        )

    try:
        # データハッシュをbytesに変換
        data_hash_bytes = None
        if request.data_hash:
            if request.data_hash.startswith('0x'):
                data_hash_bytes = bytes.fromhex(request.data_hash[2:])
            else:
                data_hash_bytes = bytes.fromhex(request.data_hash)

        # ブロックチェーンに記録
        proof_id = await blockchain_service.record_zkp_proof(
            device_id=request.device_id,
            proof=request.proof,
            public_signals=request.public_signals,
            proof_type=request.proof_type,
            data_hash=data_hash_bytes
        )

        if not proof_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record proof on blockchain"
            )

        logger.info(f"Successfully recorded proof {proof_id} for device {request.device_id}")

        return {
            "success": True,
            "proof_id": proof_id,
            "device_id": request.device_id,
            "proof_type": request.proof_type,
            "message": "ZKP proof recorded on blockchain successfully"
        }

    except Exception as e:
        logger.error(f"Failed to record proof: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record proof: {str(e)}"
        )


@router.post("/record-proof-from-csi")
async def record_zkp_proof_from_csi(
    request: RecordProofFromCSIRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    CSIデータからZKP証明を抽出してブロックチェーンに記録

    Args:
        request: CSIデータからの証明記録リクエスト
        db: データベースセッション

    Returns:
        記録結果
    """
    if not blockchain_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Blockchain service is not available"
        )

    try:
        # CSIデータ取得
        csi_data = db.query(CSIData).filter(CSIData.id == request.csi_data_id).first()

        if not csi_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CSI data not found"
            )

        # processed_dataから証明を取得
        if not csi_data.processed_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No processed data available"
            )

        base_csi_comparison = csi_data.processed_data.get("base_csi_comparison")

        if not base_csi_comparison:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No ZKP proof available for this CSI data"
            )

        proof = base_csi_comparison.get("zkp_proof")
        public_signals = base_csi_comparison.get("public_signals")

        if not proof or not public_signals:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid ZKP proof data"
            )

        # デバイスIDを取得（CSIデータのdevice_idまたはuploader_id）
        device_id = csi_data.device_id if hasattr(csi_data, 'device_id') else str(csi_data.uploader_id)

        # ブロックチェーンに記録
        proof_id = await blockchain_service.record_zkp_proof(
            device_id=device_id,
            proof=proof,
            public_signals=public_signals,
            proof_type=request.proof_type
        )

        if not proof_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record proof on blockchain"
            )

        logger.info(
            f"Successfully recorded proof {proof_id} from CSI data {request.csi_data_id}"
        )

        return {
            "success": True,
            "proof_id": proof_id,
            "csi_data_id": str(request.csi_data_id),
            "device_id": device_id,
            "proof_type": request.proof_type,
            "message": "ZKP proof from CSI data recorded on blockchain successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record proof from CSI data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record proof: {str(e)}"
        )


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
    ZKP証明を検証済みとしてブロックチェーンにマーク

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

    try:
        success = blockchain_service.verify_proof_on_chain(
            proof_id=request.proof_id,
            is_valid=request.is_valid
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to mark proof as verified on blockchain"
            )

        return {
            "success": True,
            "proof_id": request.proof_id,
            "is_valid": request.is_valid,
            "message": f"Proof marked as {'valid' if request.is_valid else 'invalid'} on blockchain"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to verify proof on chain: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify proof on chain: {str(e)}"
        )
