"""
呼吸解析サービス
"""

import uuid
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func
import logging

from app.models.breathing_analysis import BreathingAnalysis, Alert
from app.models.csi_data import CSIData
from app.models.device import Device
from app.schemas.csi_data import (
    BreathingAnalysisResult, BreathingAnalysisResponse,
    BreathingAnalysisFilter, BreathingAnalysisStats,
    AlertCreate, AlertResponse
)
from app.services.websocket import RealtimeDataService
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
        csi_data = db.query(CSIData).join(Device).filter(
            and_(
                CSIData.id == csi_data_id,
                Device.owner_id == user_id
            )
        ).first()

        if not csi_data:
            raise ValueError("CSIデータが見つからないか、アクセス権限がありません")

        # 解析結果作成
        breathing_analysis = BreathingAnalysis(
            csi_data_id=csi_data_id,
            device_id=csi_data.device_id,
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

        # WebSocketでリアルタイム解析結果を配信
        device = csi_data.device
        if device:
            await RealtimeDataService.send_breathing_analysis_update(
                device.device_id,
                {
                    "analysis_id": str(breathing_analysis.id),
                    "breathing_rate": breathing_analysis.breathing_rate,
                    "confidence_score": breathing_analysis.confidence_score,
                    "analysis_timestamp": breathing_analysis.analysis_timestamp.isoformat(),
                    "quality_metrics": breathing_analysis.quality_metrics
                }
            )

            # 異常値検出とアラート生成
            await BreathingAnalysisService._check_anomalies(
                db, breathing_analysis, device.device_id
            )

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
    async def _check_anomalies(
        db: Session,
        analysis: BreathingAnalysis,
        device_id: str
    ):
        """呼吸異常検出とアラート生成"""
        alerts_to_create = []

        # 呼吸数異常チェック
        if analysis.breathing_rate:
            if analysis.breathing_rate < 8 or analysis.breathing_rate > 40:
                severity = "high" if (analysis.breathing_rate < 6 or analysis.breathing_rate > 50) else "medium"
                alerts_to_create.append({
                    "alert_type": "breathing_rate_anomaly",
                    "severity": severity,
                    "message": f"異常な呼吸数を検出: {analysis.breathing_rate:.1f}回/分"
                })

        # 信頼度低下チェック
        if analysis.confidence_score and analysis.confidence_score < 0.5:
            alerts_to_create.append({
                "alert_type": "low_confidence",
                "severity": "low",
                "message": f"解析信頼度が低下: {analysis.confidence_score:.2f}"
            })

        # 品質メトリクス異常チェック
        if analysis.quality_metrics:
            signal_quality = analysis.quality_metrics.get("signal_quality", 1.0)
            if signal_quality < 0.3:
                alerts_to_create.append({
                    "alert_type": "poor_signal_quality",
                    "severity": "medium",
                    "message": f"信号品質が低下: {signal_quality:.2f}"
                })

        # アラート作成
        for alert_data in alerts_to_create:
            await AlertService.create_alert(
                db,
                AlertCreate(
                    device_id=device_id,
                    alert_type=alert_data["alert_type"],
                    severity=alert_data["severity"],
                    message=alert_data["message"]
                )
            )

    @staticmethod
    def get_analysis_list(
        db: Session,
        user_id: uuid.UUID,
        filters: BreathingAnalysisFilter = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[BreathingAnalysis], int]:
        """呼吸解析結果一覧取得"""

        query = db.query(BreathingAnalysis).join(Device).filter(Device.owner_id == user_id)

        # フィルター適用
        if filters:
            if filters.device_id:
                query = query.filter(Device.device_id == filters.device_id)
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

    @staticmethod
    def get_latest_analysis(
        db: Session,
        device_id: str,
        user_id: uuid.UUID
    ) -> Optional[BreathingAnalysis]:
        """最新の呼吸解析結果取得"""
        return db.query(BreathingAnalysis).join(Device).filter(
            and_(
                Device.device_id == device_id,
                Device.owner_id == user_id
            )
        ).order_by(desc(BreathingAnalysis.analysis_timestamp)).first()

    @staticmethod
    def get_device_analysis_stats(
        db: Session,
        device_id: str,
        user_id: uuid.UUID,
        days: int = 7
    ) -> BreathingAnalysisStats:
        """デバイスの呼吸解析統計情報取得（最適化版）"""

        device = db.query(Device).filter(
            and_(
                Device.device_id == device_id,
                Device.owner_id == user_id
            )
        ).first()

        if not device:
            raise ValueError("デバイスが見つかりません")

        # 期間指定
        start_date = datetime.utcnow() - timedelta(days=days)

        # 統計計算（SQL集約関数活用で効率化）
        stats_query = db.query(
            func.count(BreathingAnalysis.id).label('total_analyses'),
            func.avg(BreathingAnalysis.breathing_rate).label('avg_breathing_rate'),
            func.avg(BreathingAnalysis.confidence_score).label('avg_confidence_score'),
            func.min(BreathingAnalysis.analysis_timestamp).label('period_start'),
            func.max(BreathingAnalysis.analysis_timestamp).label('period_end')
        ).filter(
            and_(
                BreathingAnalysis.device_id == device.id,
                BreathingAnalysis.analysis_timestamp >= start_date
            )
        ).first()

        if not stats_query or stats_query.total_analyses == 0:
            return BreathingAnalysisStats(
                device_id=device_id,
                total_analyses=0,
                avg_breathing_rate=None,
                avg_confidence_score=None,
                latest_analysis=None,
                analysis_period_start=None,
                analysis_period_end=None
            )

        # 最新解析日時（別途取得）
        latest_analysis = db.query(func.max(BreathingAnalysis.analysis_timestamp)).filter(
            and_(
                BreathingAnalysis.device_id == device.id,
                BreathingAnalysis.analysis_timestamp >= start_date
            )
        ).scalar()

        return BreathingAnalysisStats(
            device_id=device_id,
            total_analyses=int(stats_query.total_analyses),
            avg_breathing_rate=float(stats_query.avg_breathing_rate) if stats_query.avg_breathing_rate else None,
            avg_confidence_score=float(stats_query.avg_confidence_score) if stats_query.avg_confidence_score else None,
            latest_analysis=latest_analysis,
            analysis_period_start=stats_query.period_start,
            analysis_period_end=stats_query.period_end
        )

    @staticmethod
    def get_breathing_trends(
        db: Session,
        device_id: str,
        user_id: uuid.UUID,
        hours: int = 24,
        cache_service: Optional[AnalysisCacheService] = None
    ) -> Dict[str, Any]:
        """呼吸トレンドデータ取得（最適化版・キャッシュ対応）"""

        # キャッシュから取得を試行
        if cache_service:
            cached_data = cache_service.get_breathing_trends(device_id, str(user_id), hours)
            if cached_data:
                return cached_data

        # デバイス検索の最適化：device_idインデックス活用
        device = db.query(Device).filter(
            and_(
                Device.device_id == device_id,
                Device.owner_id == user_id
            )
        ).first()

        if not device:
            raise ValueError("デバイスが見つかりません")

        # 時間範囲
        start_time = datetime.utcnow() - timedelta(hours=hours)

        # クエリ最適化：必要カラムのみ取得し、インデックスを効果的に活用
        # device_idとanalysis_timestampの複合インデックスを活用
        analyses = db.query(
            BreathingAnalysis.analysis_timestamp,
            BreathingAnalysis.breathing_rate,
            BreathingAnalysis.confidence_score
        ).filter(
            and_(
                BreathingAnalysis.device_id == device.id,
                BreathingAnalysis.analysis_timestamp >= start_time
            )
        ).order_by(BreathingAnalysis.analysis_timestamp).all()

        # チャート用データ構築
        breathing_rate_data = []
        confidence_data = []
        timestamps = []

        for analysis in analyses:
            timestamp_str = analysis.analysis_timestamp.isoformat()
            timestamps.append(timestamp_str)

            breathing_rate_data.append({
                "timestamp": timestamp_str,
                "value": analysis.breathing_rate
            })

            confidence_data.append({
                "timestamp": timestamp_str,
                "value": analysis.confidence_score
            })

        result = {
            "device_id": device_id,
            "period_hours": hours,
            "data_points": len(analyses),
            "timestamps": timestamps,
            "breathing_rate": breathing_rate_data,
            "confidence": confidence_data,
            "summary": {
                "avg_breathing_rate": sum(
                    [a.breathing_rate for a in analyses if a.breathing_rate]
                ) / len([a.breathing_rate for a in analyses if a.breathing_rate]) if analyses else None,
                "min_breathing_rate": min(
                    [a.breathing_rate for a in analyses if a.breathing_rate]
                ) if analyses else None,
                "max_breathing_rate": max(
                    [a.breathing_rate for a in analyses if a.breathing_rate]
                ) if analyses else None
            }
        }

        # キャッシュに保存
        if cache_service:
            cache_service.set_breathing_trends(device_id, str(user_id), hours, result)

        return result


class AlertService:
    """アラート管理サービス"""

    @staticmethod
    async def create_alert(
        db: Session,
        alert_data: AlertCreate
    ) -> Alert:
        """アラート作成"""

        # デバイス存在確認
        device = db.query(Device).filter(Device.device_id == alert_data.device_id).first()
        if not device:
            raise ValueError("デバイスが見つかりません")

        # 重複アラートチェック（同じタイプのアラートが1時間以内にある場合はスキップ）
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        existing_alert = db.query(Alert).filter(
            and_(
                Alert.device_id == device.id,
                Alert.alert_type == alert_data.alert_type,
                Alert.created_at >= one_hour_ago,
                Alert.is_acknowledged == False
            )
        ).first()

        if existing_alert:
            return existing_alert

        # アラート作成
        alert = Alert(
            device_id=device.id,
            alert_type=alert_data.alert_type,
            severity=alert_data.severity,
            message=alert_data.message,
            is_acknowledged=False
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)

        # WebSocketで通知
        await RealtimeDataService.send_system_notification({
            "type": "alert",
            "alert_id": str(alert.id),
            "device_id": alert_data.device_id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message
        })

        logger.info(f"Alert created: {alert.id} ({alert.alert_type}) for device {alert_data.device_id}")
        return alert

    @staticmethod
    def get_device_alerts(
        db: Session,
        device_id: str,
        user_id: uuid.UUID,
        include_acknowledged: bool = False,
        limit: int = 50
    ) -> List[Alert]:
        """デバイスのアラート一覧取得"""

        query = db.query(Alert).join(Device).filter(
            and_(
                Device.device_id == device_id,
                Device.owner_id == user_id
            )
        )

        if not include_acknowledged:
            query = query.filter(Alert.is_acknowledged == False)

        return query.order_by(desc(Alert.created_at)).limit(limit).all()

    @staticmethod
    async def acknowledge_alert(
        db: Session,
        alert_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> Optional[Alert]:
        """アラート確認"""

        alert = db.query(Alert).join(Device).filter(
            and_(
                Alert.id == alert_id,
                Device.owner_id == user_id
            )
        ).first()

        if not alert:
            return None

        alert.is_acknowledged = True
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.utcnow()

        db.commit()
        db.refresh(alert)

        # WebSocketで確認通知
        device = alert.device
        if device:
            await RealtimeDataService.send_system_notification({
                "type": "alert_acknowledged",
                "alert_id": str(alert.id),
                "device_id": device.device_id,
                "acknowledged_by": str(user_id)
            })

        return alert