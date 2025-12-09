"""
呼吸解析結果関連エンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
import math

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.breathing_analysis import BreathingAnalysisService
from app.schemas.csi_data import (
    BreathingAnalysisResult, BreathingAnalysisResponse, BreathingAnalysisListResponse,
    BreathingAnalysisFilter, BreathingAnalysisStats,
)

router = APIRouter()


@router.post("/", response_model=BreathingAnalysisResponse)
async def create_analysis_result(
    csi_data_id: uuid.UUID,
    analysis_data: BreathingAnalysisResult,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    呼吸解析結果作成
    """
    try:
        analysis = await BreathingAnalysisService.create_analysis_result(
            db, csi_data_id, analysis_data, current_user.id
        )

        return BreathingAnalysisResponse(
            id=analysis.id,
            csi_data_id=analysis.csi_data_id,
            breathing_rate=analysis.breathing_rate,
            confidence_score=analysis.confidence_score,
            analysis_timestamp=analysis.analysis_timestamp,
            window_start=analysis.window_start,
            window_end=analysis.window_end,
            frequency_domain_data=analysis.frequency_domain_data,
            time_domain_data=analysis.time_domain_data,
            quality_metrics=analysis.quality_metrics,
            ipfs_hash=analysis.ipfs_hash,
            blockchain_tx_hash=analysis.blockchain_tx_hash,
            created_at=analysis.created_at,
            updated_at=analysis.updated_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解析結果作成に失敗しました: {str(e)}"
        )
