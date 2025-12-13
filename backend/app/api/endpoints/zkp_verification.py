"""
ZKP検証エンドポイント

第三者がZKP証明を検証するためのエンドポイント
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
import logging

from app.core.database import get_db
from app.models.csi_data import CSIData
from app.services.zkp_service import ZKPService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/csi-data/{csi_data_id}/proof")
async def get_zkp_proof(
    csi_data_id: UUID,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    CSIデータのZKP証明を取得

    Args:
        csi_data_id: CSIデータID
        db: データベースセッション

    Returns:
        ZKP証明データ
    """
    # CSIデータ取得
    csi_data = db.query(CSIData).filter(CSIData.id == csi_data_id).first()

    if not csi_data:
        raise HTTPException(status_code=404, detail="CSI data not found")

    # processed_dataから証明を取得
    if not csi_data.processed_data:
        raise HTTPException(status_code=404, detail="No processed data available")

    base_csi_comparison = csi_data.processed_data.get("base_csi_comparison")

    if not base_csi_comparison:
        raise HTTPException(status_code=404, detail="No ZKP proof available for this CSI data")

    return {
        "csi_data_id": str(csi_data.id),
        "base_csi_id": base_csi_comparison.get("base_csi_id"),
        "base_csi_name": base_csi_comparison.get("base_csi_name"),
        "similarity_score": base_csi_comparison.get("similarity_score"),
        "zkp_proof": base_csi_comparison.get("zkp_proof"),
        "public_signals": base_csi_comparison.get("public_signals"),
        "is_valid": base_csi_comparison.get("is_valid"),
        "data_dimensions": base_csi_comparison.get("data_dimensions"),
        "created_at": csi_data.created_at.isoformat() if csi_data.created_at else None
    }


@router.post("/verify")
async def verify_zkp_proof(
    proof_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    ZKP証明を検証

    Args:
        proof_data: 検証するデータ
            - proof: ZKP証明
            - publicSignals: 公開信号

    Returns:
        検証結果
    """
    try:
        proof = proof_data.get("proof")
        public_signals = proof_data.get("publicSignals")

        if not proof or not public_signals:
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: proof and publicSignals"
            )

        # ZKPサービスで検証
        zkp_service = ZKPService()
        is_valid = await zkp_service.verify_full_cosine_similarity_proof(
            proof=proof,
            public_signals=public_signals
        )

        logger.info(f"ZKP verification result: {is_valid}")

        return {
            "is_valid": is_valid,
            "message": "Proof is valid" if is_valid else "Proof is invalid"
        }

    except Exception as e:
        logger.error(f"ZKP verification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Verification failed: {str(e)}"
        )


@router.get("/csi-data/{csi_data_id}/verify")
async def verify_csi_data_proof(
    csi_data_id: UUID,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    CSIデータのZKP証明を取得して検証

    Args:
        csi_data_id: CSIデータID
        db: データベースセッション

    Returns:
        検証結果
    """
    # CSIデータ取得
    csi_data = db.query(CSIData).filter(CSIData.id == csi_data_id).first()

    if not csi_data:
        raise HTTPException(status_code=404, detail="CSI data not found")

    # processed_dataから証明を取得
    if not csi_data.processed_data:
        raise HTTPException(status_code=404, detail="No processed data available")

    base_csi_comparison = csi_data.processed_data.get("base_csi_comparison")

    if not base_csi_comparison:
        raise HTTPException(status_code=404, detail="No ZKP proof available for this CSI data")

    proof = base_csi_comparison.get("zkp_proof")
    public_signals = base_csi_comparison.get("public_signals")

    if not proof or not public_signals:
        raise HTTPException(
            status_code=404,
            detail="Incomplete ZKP proof data"
        )

    try:
        # ZKPサービスで検証
        zkp_service = ZKPService()
        is_valid = await zkp_service.verify_full_cosine_similarity_proof(
            proof=proof,
            public_signals=public_signals
        )

        logger.info(f"ZKP verification for CSI data {csi_data_id}: {is_valid}")

        return {
            "csi_data_id": str(csi_data.id),
            "base_csi_id": base_csi_comparison.get("base_csi_id"),
            "base_csi_name": base_csi_comparison.get("base_csi_name"),
            "similarity_score": base_csi_comparison.get("similarity_score"),
            "is_valid": is_valid,
            "verification_result": "Proof is valid" if is_valid else "Proof is invalid",
            "data_dimensions": base_csi_comparison.get("data_dimensions"),
            "verified_at": csi_data.created_at.isoformat() if csi_data.created_at else None
        }

    except Exception as e:
        logger.error(f"ZKP verification failed for CSI data {csi_data_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Verification failed: {str(e)}"
        )
