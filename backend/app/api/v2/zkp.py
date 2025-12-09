"""
ZKP API エンドポイント

CSI呼吸解析のZero-Knowledge Proof生成・検証API
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.zkp import (
    ZKPProofRequest,
    ZKPProofResponse,
    ZKPVerifyRequest,
    ZKPVerifyResponse,
)
from app.services.zkp_service import ZKPService
from app.services.breathing_analysis import BreathingAnalysisService

logger = logging.getLogger(__name__)

router = APIRouter()

# ZKPサービスのインスタンス（シングルトン）
zkp_service = None


def get_zkp_service() -> ZKPService:
    """ZKPサービスの取得"""
    global zkp_service
    if zkp_service is None:
        try:
            zkp_service = ZKPService()
        except Exception as e:
            logger.error(f"Failed to initialize ZKP service: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ZKP service is not available. Please ensure zkp environment is set up.",
            )
    return zkp_service


@router.post("/breathing-analysis/{analysis_id}/zkp", response_model=ZKPProofResponse)
async def generate_zkp_proof(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    zkp_service: ZKPService = Depends(get_zkp_service),
):
    """
    呼吸解析結果のZKP証明を生成

    Args:
        analysis_id: 呼吸解析結果ID
        db: データベースセッション
        current_user: 現在のユーザー
        zkp_service: ZKPサービス

    Returns:
        ZKP証明データ
    """
    logger.info(f"Generating ZKP for analysis {analysis_id} by user {current_user.id}")

    # 呼吸解析結果の取得
    breathing_service = BreathingAnalysisService(db)
    analysis_result = await breathing_service.get_analysis_result(analysis_id)

    if not analysis_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Breathing analysis {analysis_id} not found",
        )

    try:
        # ZKP証明の生成
        proof_data = await zkp_service.generate_proof(
            csi_data=analysis_result.csi_amplitude_series,
            breathing_rate=analysis_result.breathing_rate,
            breathing_frequency=analysis_result.breathing_frequency,
            confidence_score=analysis_result.confidence,
            timestamp=analysis_result.timestamp,
        )

        return ZKPProofResponse(
            analysisId=analysis_id,
            proof=proof_data["proof"],
            publicSignals=proof_data["publicSignals"],
            commitment=proof_data["commitment"],
            metadata=proof_data["metadata"],
        )

    except Exception as e:
        logger.error(f"ZKP generation failed for analysis {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate ZKP: {str(e)}",
        )


@router.post("/zkp/verify", response_model=ZKPVerifyResponse)
async def verify_zkp_proof(
    request: ZKPVerifyRequest,
    zkp_service: ZKPService = Depends(get_zkp_service),
):
    """
    ZKP証明の検証

    Args:
        request: 検証リクエスト
        zkp_service: ZKPサービス

    Returns:
        検証結果
    """
    logger.info("Verifying ZKP proof")

    try:
        is_valid = await zkp_service.verify_proof(
            proof=request.proof, public_signals=request.publicSignals
        )

        return ZKPVerifyResponse(
            isValid=is_valid,
            publicSignals=request.publicSignals,
            message="Proof is valid" if is_valid else "Proof is invalid",
        )

    except Exception as e:
        logger.error(f"ZKP verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify ZKP: {str(e)}",
        )


@router.post("/breathing-analysis/batch-zkp", response_model=list[ZKPProofResponse])
async def generate_batch_zkp_proofs(
    request: ZKPProofRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    zkp_service: ZKPService = Depends(get_zkp_service),
):
    """
    複数の呼吸解析結果のZKP証明をバッチ生成

    Args:
        request: バッチ証明生成リクエスト
        db: データベースセッション
        current_user: 現在のユーザー
        zkp_service: ZKPサービス

    Returns:
        ZKP証明データのリスト
    """
    logger.info(
        f"Generating batch ZKP for {len(request.analysisIds)} analyses by user {current_user.id}"
    )

    results = []
    breathing_service = BreathingAnalysisService(db)

    for analysis_id in request.analysisIds:
        try:
            # 呼吸解析結果の取得
            analysis_result = await breathing_service.get_analysis_result(analysis_id)

            if not analysis_result:
                logger.warning(f"Analysis {analysis_id} not found, skipping")
                continue

            # ZKP証明の生成
            proof_data = await zkp_service.generate_proof(
                csi_data=analysis_result.csi_amplitude_series,
                breathing_rate=analysis_result.breathing_rate,
                breathing_frequency=analysis_result.breathing_frequency,
                confidence_score=analysis_result.confidence,
                timestamp=analysis_result.timestamp,
            )

            results.append(
                ZKPProofResponse(
                    analysisId=analysis_id,
                    proof=proof_data["proof"],
                    publicSignals=proof_data["publicSignals"],
                    commitment=proof_data["commitment"],
                    metadata=proof_data["metadata"],
                )
            )

        except Exception as e:
            logger.error(f"Failed to generate ZKP for analysis {analysis_id}: {e}")
            # エラーが発生しても他の証明生成を続行

    return results
