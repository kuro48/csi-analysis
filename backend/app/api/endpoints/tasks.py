"""
タスクキュー管理エンドポイント
"""

import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.analysis_tasks import register_task_handlers
from app.services.task_queue import TaskPriority, task_queue

router = APIRouter()


@router.post("/analysis/breathing")
async def queue_breathing_analysis(
    csi_data_id: str = Body(..., description="CSIデータID"),
    analysis_params: Dict[str, Any] = Body(default={}, description="解析パラメータ"),
    priority: str = Body(default="normal", description="優先度 (low, normal, high, urgent)"),
    current_user: User = Depends(get_current_user),
):
    """
    呼吸解析タスクをキューに追加
    """
    try:
        # 優先度の変換
        priority_map = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.NORMAL,
            "high": TaskPriority.HIGH,
            "urgent": TaskPriority.URGENT,
        }
        task_priority = priority_map.get(priority, TaskPriority.NORMAL)

        # タスクをキューに追加
        task_id = await task_queue.enqueue_task(
            "csi_breathing_analysis",
            {"csi_data_id": csi_data_id, "analysis_params": analysis_params, "user_id": str(current_user.id)},
            priority=task_priority,
        )

        return {
            "task_id": task_id,
            "task_type": "csi_breathing_analysis",
            "status": "queued",
            "priority": priority,
            "csi_data_id": csi_data_id,
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"タスクのキューへの追加に失敗しました: {str(e)}")


@router.post("/analysis/batch")
async def queue_batch_analysis(
    csi_data_ids: List[str] = Body(..., description="CSIデータIDリスト"),
    analysis_params: Dict[str, Any] = Body(default={}, description="解析パラメータ"),
    priority: str = Body(default="normal", description="優先度"),
    current_user: User = Depends(get_current_user),
):
    """
    バッチ解析タスクをキューに追加
    """
    try:
        if len(csi_data_ids) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSIデータIDリストが空です")

        if len(csi_data_ids) > 100:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="一度に処理できるCSIデータは100件までです")

        # 優先度の変換
        priority_map = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.NORMAL,
            "high": TaskPriority.HIGH,
            "urgent": TaskPriority.URGENT,
        }
        task_priority = priority_map.get(priority, TaskPriority.NORMAL)

        # バッチタスクをキューに追加
        task_id = await task_queue.enqueue_task(
            "batch_analysis",
            {"csi_data_ids": csi_data_ids, "analysis_params": analysis_params, "user_id": str(current_user.id)},
            priority=task_priority,
        )

        return {
            "task_id": task_id,
            "task_type": "batch_analysis",
            "status": "queued",
            "priority": priority,
            "total_items": len(csi_data_ids),
            "csi_data_ids": csi_data_ids,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"バッチタスクのキューへの追加に失敗しました: {str(e)}",
        )


@router.get("/status/{task_id}")
async def get_task_status(task_id: str, current_user: User = Depends(get_current_user)):
    """
    タスクステータス取得
    """
    try:
        task_status = await task_queue.get_task_status(task_id)

        if not task_status:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="タスクが見つかりません")

        return {
            "task_id": task_id,
            "status": task_status["status"],
            "task_type": task_status["task_type"],
            "created_at": task_status["created_at"],
            "started_at": task_status.get("started_at"),
            "completed_at": task_status.get("completed_at"),
            "retries": task_status.get("retries", 0),
            "error_message": task_status.get("error_message"),
            "result": task_status.get("result"),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"タスクステータス取得に失敗しました: {str(e)}")


@router.get("/queue/stats")
async def get_queue_stats(current_user: User = Depends(get_current_user)):
    """
    キュー統計情報取得
    """
    try:
        stats = await task_queue.get_queue_stats()

        return {
            "queue_stats": stats,
            "worker_status": "running" if task_queue.is_running else "stopped",
            "active_workers": len(task_queue.worker_tasks),
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"キュー統計情報取得に失敗しました: {str(e)}")


@router.post("/maintenance")
async def queue_maintenance_task(
    maintenance_type: str = Body(..., description="メンテナンス種別"), current_user: User = Depends(get_current_user)
):
    """
    システムメンテナンスタスクをキューに追加（管理者のみ）
    """
    # 管理者権限チェック
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理者権限が必要です")

    try:
        valid_types = ["cleanup_old_files", "ipfs_gc", "database_optimize", "general"]
        if maintenance_type not in valid_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"無効なメンテナンス種別です。有効な値: {valid_types}")

        # メンテナンスタスクをキューに追加
        task_id = await task_queue.enqueue_task(
            "system_maintenance",
            {"maintenance_type": maintenance_type, "requested_by": str(current_user.id)},
            priority=TaskPriority.HIGH,
        )

        return {
            "task_id": task_id,
            "task_type": "system_maintenance",
            "maintenance_type": maintenance_type,
            "status": "queued",
            "priority": "high",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"メンテナンスタスクのキューへの追加に失敗しました: {str(e)}",
        )


@router.post("/workers/start")
async def start_workers(
    num_workers: int = Body(default=3, description="ワーカー数"), current_user: User = Depends(get_current_user)
):
    """
    タスクワーカー開始（管理者のみ）
    """
    # 管理者権限チェック
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理者権限が必要です")

    try:
        if task_queue.is_running:
            return {"message": "ワーカーは既に実行中です", "active_workers": len(task_queue.worker_tasks)}

        if num_workers < 1 or num_workers > 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ワーカー数は1-10の範囲で指定してください")

        # タスクハンドラー登録
        register_task_handlers()

        # ワーカー開始
        await task_queue.start_workers(num_workers)

        return {
            "message": f"{num_workers}個のワーカーを開始しました",
            "active_workers": num_workers,
            "status": "running",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"ワーカー開始に失敗しました: {str(e)}")


@router.post("/workers/stop")
async def stop_workers(current_user: User = Depends(get_current_user)):
    """
    タスクワーカー停止（管理者のみ）
    """
    # 管理者権限チェック
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理者権限が必要です")

    try:
        if not task_queue.is_running:
            return {"message": "ワーカーは既に停止しています", "active_workers": 0}

        # ワーカー停止
        await task_queue.stop_workers()

        return {"message": "全ワーカーを停止しました", "active_workers": 0, "status": "stopped"}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"ワーカー停止に失敗しました: {str(e)}")
