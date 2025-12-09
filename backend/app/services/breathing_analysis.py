"""
呼吸解析サービス
"""

import uuid
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func
import logging

from app.models.breathing_analysis import BreathingAnalysis
from app.models.csi_data import CSIData
from app.schemas.csi_data import (
    BreathingAnalysisResult, BreathingAnalysisResponse,
    BreathingAnalysisFilter, BreathingAnalysisStats,
)
from app.services.cache import AnalysisCacheService

logger = logging.getLogger(__name__)

# ZKPサービスの遅延インポート（循環インポート回避）
_zkp_service = None


def get_zkp_service():
    """ZKPサービスの取得（遅延初期化）"""
    global _zkp_service
    if _zkp_service is None:
        try:
            from app.services.zkp_service import ZKPService
            _zkp_service = ZKPService()
        except Exception as e:
            logger.warning(f"ZKP service not available: {e}")
            _zkp_service = None
    return _zkp_service


class BreathingAnalysisService:
    """呼吸解析結果管理サービス"""

    @staticmethod
    async def create_analysis_result(
        db: Session,
        csi_data_id: uuid.UUID,
        analysis_data: BreathingAnalysisResult,
        user_id: uuid.UUID,
        generate_zkp: bool = False
    ) -> BreathingAnalysis:
        """
        呼吸解析結果作成

        Args:
            db: データベースセッション
            csi_data_id: CSIデータID
            analysis_data: 解析結果データ
            user_id: ユーザーID
            generate_zkp: ZKP証明を自動生成するかどうか（デフォルト: False）

        Returns:
            作成された呼吸解析結果
        """

        # CSIデータの存在確認と所有者チェック
        csi_data = db.query(CSIData).filter(
            and_(
                CSIData.id == csi_data_id
            )
        ).first()

        if not csi_data:
            raise ValueError("CSIデータが見つからないか、アクセス権限がありません")

        # 解析結果作成
        breathing_analysis = BreathingAnalysis(
            csi_data_id=csi_data_id,
            breathing_rate=analysis_data.breathing_rate,
            confidence_score=analysis_data.confidence_score,
            analysis_timestamp=analysis_data.analysis_timestamp,
            window_start=analysis_data.window_start,
            window_end=analysis_data.window_end,
            frequency_domain_data=analysis_data.frequency_domain_data,
            time_domain_data=analysis_data.time_domain_data,
            quality_metrics=analysis_data.quality_metrics
        )

        db.add(breathing_analysis)
        db.commit()
        db.refresh(breathing_analysis)

        # ZKP証明の自動生成（オプション）
        if generate_zkp:
            try:
                zkp_service = get_zkp_service()
                if zkp_service:
                    logger.info(f"Generating ZKP for analysis {breathing_analysis.id}")
                    # 非同期でZKP証明を生成（失敗してもメイン処理は継続）
                    import asyncio
                    asyncio.create_task(
                        BreathingAnalysisService._generate_zkp_async(
                            zkp_service,
                            analysis_data,
                            breathing_analysis.id
                        )
                    )
                else:
                    logger.warning("ZKP service not available, skipping ZKP generation")
            except Exception as e:
                logger.error(f"Failed to initiate ZKP generation: {e}")
                # ZKP生成失敗はメイン処理に影響させない

        logger.info(f"Breathing analysis created: {breathing_analysis.id}")
        return breathing_analysis

    @staticmethod
    async def _generate_zkp_async(
        zkp_service,
        analysis_data: BreathingAnalysisResult,
        analysis_id: uuid.UUID
    ):
        """
        ZKP証明の非同期生成

        Args:
            zkp_service: ZKPサービスインスタンス
            analysis_data: 解析結果データ
            analysis_id: 解析結果ID
        """
        try:
            # CSI振幅データを取得
            # Note: time_domain_dataに振幅時系列が含まれていると仮定
            csi_amplitude = analysis_data.time_domain_data.get("amplitude_series", [])

            # 呼吸周波数を計算（呼吸数から換算）
            breathing_frequency = analysis_data.breathing_rate / 60.0  # Hz

            # ZKP証明生成
            proof_data = await zkp_service.generate_proof(
                csi_data=csi_amplitude,
                breathing_rate=analysis_data.breathing_rate,
                breathing_frequency=breathing_frequency,
                confidence_score=analysis_data.confidence_score,
                timestamp=analysis_data.analysis_timestamp,
            )

            logger.info(f"ZKP proof generated for analysis {analysis_id}")

        except Exception as e:
            logger.error(f"Failed to generate ZKP for analysis {analysis_id}: {e}")

    @staticmethod
    def get_analysis_list(
        db: Session,
        user_id: uuid.UUID,
        filters: BreathingAnalysisFilter = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[BreathingAnalysis], int]:
        """呼吸解析結果一覧取得"""

        query = db.query(BreathingAnalysis)

        # フィルター適用
        if filters:
            if filters.start_date:
                query = query.filter(BreathingAnalysis.analysis_timestamp >= filters.start_date)
            if filters.end_date:
                query = query.filter(BreathingAnalysis.analysis_timestamp <= filters.end_date)
            if filters.min_confidence:
                query = query.filter(BreathingAnalysis.confidence_score >= filters.min_confidence)

        # 総件数取得
        total_count = query.count()

        # ページネーション適用
        offset = (page - 1) * page_size
        analyses = query.order_by(desc(BreathingAnalysis.analysis_timestamp)).offset(offset).limit(page_size).all()

        return analyses, total_count