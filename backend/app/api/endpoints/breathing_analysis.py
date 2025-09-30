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
from app.services.breathing_analysis import BreathingAnalysisService, AlertService
from app.schemas.csi_data import (
    BreathingAnalysisResult, BreathingAnalysisResponse, BreathingAnalysisListResponse,
    BreathingAnalysisFilter, BreathingAnalysisStats,
    AlertCreate, AlertResponse
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

        device = analysis.device
        return BreathingAnalysisResponse(
            id=analysis.id,
            csi_data_id=analysis.csi_data_id,
            device_id=device.device_id if device else "unknown",
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


@router.get("/results/{device_id}", response_model=BreathingAnalysisListResponse)
async def get_device_analysis_results(
    device_id: str,
    start_date: Optional[str] = Query(None, description="開始日時"),
    end_date: Optional[str] = Query(None, description="終了日時"),
    min_confidence: Optional[float] = Query(None, description="最小信頼度"),
    page: int = Query(1, ge=1, description="ページ番号"),
    page_size: int = Query(50, ge=1, le=200, description="1ページあたりの件数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    デバイスの呼吸解析結果一覧取得
    """
    try:
        from datetime import datetime

        # フィルター構築
        filters = BreathingAnalysisFilter(
            device_id=device_id,
            start_date=datetime.fromisoformat(start_date) if start_date else None,
            end_date=datetime.fromisoformat(end_date) if end_date else None,
            min_confidence=min_confidence
        )

        analyses, total_count = BreathingAnalysisService.get_analysis_list(
            db, current_user.id, filters, page, page_size
        )

        # レスポンス構築
        analysis_responses = []
        for analysis in analyses:
            device = analysis.device
            analysis_response = BreathingAnalysisResponse(
                id=analysis.id,
                csi_data_id=analysis.csi_data_id,
                device_id=device.device_id if device else "unknown",
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
            analysis_responses.append(analysis_response)

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

        return BreathingAnalysisListResponse(
            analyses=analysis_responses,
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解析結果一覧取得に失敗しました: {str(e)}"
        )


@router.get("/results/{device_id}/latest", response_model=BreathingAnalysisResponse)
async def get_latest_analysis_result(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    最新の呼吸解析結果取得
    """
    analysis = BreathingAnalysisService.get_latest_analysis(db, device_id, current_user.id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="解析結果が見つかりません"
        )

    device = analysis.device
    return BreathingAnalysisResponse(
        id=analysis.id,
        csi_data_id=analysis.csi_data_id,
        device_id=device.device_id if device else "unknown",
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


@router.get("/trends/{device_id}")
async def get_breathing_trends(
    device_id: str,
    hours: int = Query(24, ge=1, le=168, description="期間（時間）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    呼吸トレンドデータ取得
    """
    try:
        trends = BreathingAnalysisService.get_breathing_trends(
            db, device_id, current_user.id, hours
        )
        return trends
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"トレンドデータ取得に失敗しました: {str(e)}"
        )