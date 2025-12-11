"""
CSI解析バッチタスクハンドラー
"""

import asyncio
import logging
import numpy as np
from typing import Dict, Any
from datetime import datetime
import uuid

from app.services.task_queue import task_queue, TaskPriority
from app.core.database import SessionLocal
from app.models.csi_data import CSIData
from app.models.breathing_analysis import BreathingAnalysis

logger = logging.getLogger(__name__)


async def csi_breathing_analysis_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    CSI呼吸解析タスク

    Args:
        payload: タスクペイロード
            - csi_data_id: CSIデータID
            - analysis_params: 解析パラメータ
            - generate_zkp: ZKP証明を自動生成するかどうか（オプション）

    Returns:
        解析結果辞書
    """
    csi_data_id = payload.get("csi_data_id")
    analysis_params = payload.get("analysis_params", {})
    generate_zkp = payload.get("generate_zkp", False)

    logger.info(f"Starting breathing analysis for CSI data: {csi_data_id} (generate_zkp={generate_zkp})")

    try:
        # データベースからCSIデータ取得
        db = SessionLocal()
        try:
            csi_data = db.query(CSIData).filter(CSIData.id == uuid.UUID(csi_data_id)).first()
            if not csi_data:
                raise ValueError(f"CSI data not found: {csi_data_id}")

            # ファイルデータまたはprocessed_dataから解析データを取得
            file_data = None
            if csi_data.file_path:
                # RESEARCH_MODE: ファイルから読み込み
                try:
                    with open(csi_data.file_path, 'rb') as f:
                        file_data = f.read()
                    logger.info(f"Loaded file data from: {csi_data.file_path}")
                except Exception as e:
                    logger.warning(f"Failed to load file, using processed_data instead: {e}")
                    # ファイル読み込み失敗時はprocessed_dataを使用
                    file_data = None

            if file_data is None and csi_data.processed_data:
                # 本番モード: processed_dataから解析データを取得
                logger.info("Using processed_data for analysis (PRODUCTION MODE)")
                # processed_dataを使用した解析（詳細は実装依存）
                # ここでは模擬的にファイルデータとして扱う
                import json
                processed_data_str = csi_data.processed_data if isinstance(csi_data.processed_data, str) else json.dumps(csi_data.processed_data)
                file_data = processed_data_str.encode('utf-8')

            if file_data is None:
                raise ValueError("No data available for analysis (neither file_path nor processed_data)")

            # 呼吸解析実行（模擬実装）
            analysis_result = await perform_breathing_analysis(file_data, analysis_params)

            # 解析結果をデータベースに保存
            breathing_analysis = BreathingAnalysis(
                csi_data_id=csi_data.id,
                breathing_rate=analysis_result["breathing_rate"],
                confidence_score=analysis_result["confidence_score"],
                analysis_timestamp=datetime.utcnow(),
                window_start=None,  # 実際の実装では解析ウィンドウの開始時刻を設定
                window_end=None,    # 実際の実装では解析ウィンドウの終了時刻を設定
                time_domain_data={
                    "breathing_pattern": analysis_result.get("breathing_pattern", []),
                    "algorithm_version": analysis_result.get("algorithm_version", "1.0.0")
                },
                frequency_domain_data=None,  # 実際の実装では周波数域データを設定
                quality_metrics=analysis_result.get("quality_metrics", {})
            )

            db.add(breathing_analysis)
            db.commit()
            db.refresh(breathing_analysis)

            logger.info(f"Breathing analysis completed: {breathing_analysis.id}")

            # ZKP証明の自動生成
            zkp_proof_id = None
            if generate_zkp:
                try:
                    from app.services.breathing_analysis import get_zkp_service
                    from app.schemas.csi_data import BreathingAnalysisResult

                    zkp_service = get_zkp_service()
                    if zkp_service:
                        logger.info(f"Generating ZKP proof for breathing analysis {breathing_analysis.id}")

                        # BreathingAnalysisResultスキーマを作成
                        analysis_result_schema = BreathingAnalysisResult(
                            breathing_rate=breathing_analysis.breathing_rate,
                            confidence_score=breathing_analysis.confidence_score,
                            analysis_timestamp=breathing_analysis.analysis_timestamp,
                            window_start=breathing_analysis.window_start,
                            window_end=breathing_analysis.window_end,
                            time_domain_data=breathing_analysis.time_domain_data,
                            frequency_domain_data=breathing_analysis.frequency_domain_data,
                            quality_metrics=breathing_analysis.quality_metrics
                        )

                        # ZKP証明生成（非同期）
                        from app.services.breathing_analysis import BreathingAnalysisService
                        asyncio.create_task(
                            BreathingAnalysisService._generate_zkp_async(
                                zkp_service,
                                analysis_result_schema,
                                breathing_analysis.id
                            )
                        )
                        logger.info(f"ZKP generation task created for analysis {breathing_analysis.id}")
                    else:
                        logger.warning("ZKP service not available, skipping ZKP generation")
                except Exception as e:
                    logger.error(f"Failed to initiate ZKP generation: {e}")
                    # ZKP生成失敗はメイン処理に影響させない

            return {
                "analysis_id": str(breathing_analysis.id),
                "breathing_rate": analysis_result["breathing_rate"],
                "confidence_score": analysis_result["confidence_score"],
                "processing_time": analysis_result["processing_time"],
                "zkp_generated": generate_zkp,
                "status": "completed"
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Breathing analysis task failed: {e}")
        raise


async def perform_breathing_analysis(file_data: bytes, params: Dict) -> Dict[str, Any]:
    """
    実際の呼吸解析処理（模擬実装）

    Args:
        file_data: CSIデータファイル
        params: 解析パラメータ

    Returns:
        解析結果
    """
    start_time = datetime.utcnow()

    # 模擬解析（実際の実装では信号処理を行う）
    await asyncio.sleep(2)  # 解析時間をシミュレート

    # ランダムな結果生成（実際の実装では真の解析結果）
    import random
    breathing_rate = round(random.uniform(12.0, 25.0), 1)
    confidence_score = round(random.uniform(0.7, 0.99), 2)

    # 呼吸パターン生成（模擬）
    pattern_length = 60  # 60秒間のパターン
    breathing_pattern = []
    for i in range(pattern_length):
        amplitude = np.sin(2 * np.pi * i * breathing_rate / 60) + random.uniform(-0.1, 0.1)
        breathing_pattern.append(round(amplitude, 3))

    processing_time = (datetime.utcnow() - start_time).total_seconds()

    analysis_result = {
        "breathing_rate": breathing_rate,
        "confidence_score": confidence_score,
        "breathing_pattern": breathing_pattern,
        "analysis_params": params,
        "file_size": len(file_data),
        "processing_time": processing_time,
        "algorithm_version": "1.0.0",
        "quality_metrics": {
            "signal_quality": round(random.uniform(0.6, 0.95), 2),
            "noise_level": round(random.uniform(0.05, 0.2), 2),
            "stability": round(random.uniform(0.7, 0.95), 2)
        }
    }

    return analysis_result


async def batch_analysis_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    バッチ解析タスク（複数CSIデータの一括解析）

    Args:
        payload: タスクペイロード
            - csi_data_ids: CSIデータIDリスト
            - analysis_params: 解析パラメータ

    Returns:
        バッチ解析結果
    """
    csi_data_ids = payload.get("csi_data_ids", [])
    analysis_params = payload.get("analysis_params", {})

    logger.info(f"Starting batch analysis for {len(csi_data_ids)} CSI data items")

    results = []
    failed_count = 0

    for csi_data_id in csi_data_ids:
        try:
            # 個別解析タスクをキューに追加
            task_id = await task_queue.enqueue_task(
                "csi_breathing_analysis",
                {
                    "csi_data_id": csi_data_id,
                    "analysis_params": analysis_params
                },
                priority=TaskPriority.NORMAL
            )

            results.append({
                "csi_data_id": csi_data_id,
                "task_id": task_id,
                "status": "queued"
            })

        except Exception as e:
            failed_count += 1
            results.append({
                "csi_data_id": csi_data_id,
                "status": "failed",
                "error": str(e)
            })

    return {
        "batch_id": str(uuid.uuid4()),
        "total_items": len(csi_data_ids),
        "queued_items": len(csi_data_ids) - failed_count,
        "failed_items": failed_count,
        "results": results,
        "status": "batch_queued"
    }


async def system_maintenance_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    システムメンテナンスタスク

    Args:
        payload: タスクペイロード
            - maintenance_type: メンテナンス種別

    Returns:
        メンテナンス結果
    """
    maintenance_type = payload.get("maintenance_type", "general")

    logger.info(f"Starting system maintenance: {maintenance_type}")

    start_time = datetime.utcnow()
    maintenance_results = {
        "maintenance_type": maintenance_type,
        "started_at": start_time.isoformat(),
        "tasks_completed": []
    }

    try:
        if maintenance_type == "cleanup_old_files":
            # 古いファイルクリーンアップ
            await asyncio.sleep(1)  # 模擬処理
            maintenance_results["tasks_completed"].append("old_files_cleaned")

        elif maintenance_type == "cleanup_zkp_data":
            # ZKP証明生成後のCSIデータクリーンアップ（本番モード用）
            from app.core.config import settings
            from pathlib import Path

            db = SessionLocal()
            try:
                # ZKP_DATA_RETENTION_HOURSが0の場合は即座に削除、それ以外は指定時間後に削除
                if settings.ZKP_DATA_RETENTION_HOURS >= 0:
                    retention_time = datetime.utcnow() - timedelta(hours=settings.ZKP_DATA_RETENTION_HOURS)

                    # ZKP証明が生成されているCSIデータを取得
                    from sqlalchemy import exists
                    from app.models.breathing_analysis import BreathingAnalysis

                    csi_data_to_cleanup = db.query(CSIData).join(
                        BreathingAnalysis
                    ).filter(
                        CSIData.created_at < retention_time,
                        CSIData.file_path.isnot(None),
                        BreathingAnalysis.zkp_proof.isnot(None)  # ZKP証明が存在する
                    ).all()

                    cleaned_count = 0
                    for csi_data in csi_data_to_cleanup:
                        try:
                            # ファイル削除
                            if csi_data.file_path and Path(csi_data.file_path).exists():
                                Path(csi_data.file_path).unlink()
                                logger.info(f"Deleted CSI file: {csi_data.file_path}")

                            # データベースレコードのfile_pathとraw_dataをクリア
                            csi_data.file_path = None
                            csi_data.raw_data = None
                            csi_data.file_size = None

                            cleaned_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to cleanup CSI data {csi_data.id}: {e}")

                    db.commit()
                    maintenance_results["cleaned_count"] = cleaned_count
                    maintenance_results["tasks_completed"].append(f"zkp_data_cleaned_{cleaned_count}_items")
                    logger.info(f"Cleaned up {cleaned_count} CSI data items after ZKP generation")

            finally:
                db.close()

        elif maintenance_type == "ipfs_gc":
            # IPFS ガベージコレクション
            await asyncio.sleep(2)  # 模擬処理
            maintenance_results["tasks_completed"].append("ipfs_garbage_collected")

        elif maintenance_type == "database_optimize":
            # データベース最適化
            await asyncio.sleep(3)  # 模擬処理
            maintenance_results["tasks_completed"].append("database_optimized")

        else:
            # 一般メンテナンス
            await asyncio.sleep(1)
            maintenance_results["tasks_completed"].append("general_maintenance")

        end_time = datetime.utcnow()
        maintenance_results.update({
            "completed_at": end_time.isoformat(),
            "duration": (end_time - start_time).total_seconds(),
            "status": "completed"
        })

        logger.info(f"System maintenance completed: {maintenance_type}")
        return maintenance_results

    except Exception as e:
        logger.error(f"System maintenance failed: {e}")
        raise


def register_task_handlers():
    """タスクハンドラーを登録"""
    task_queue.register_handler("csi_breathing_analysis", csi_breathing_analysis_task)
    task_queue.register_handler("batch_analysis", batch_analysis_task)
    task_queue.register_handler("system_maintenance", system_maintenance_task)
    logger.info("Analysis task handlers registered")