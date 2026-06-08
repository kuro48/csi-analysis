"""
ベースCSI管理エンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException, status as http_status, File, UploadFile, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import math
import logging
from pathlib import Path

from app.core.database import get_db
from app.core.database import SessionLocal
from app.services.base_csi import BaseCSIService
from app.services.pcap_analyzer_pipeline import SUPPORTED_CSI_EXTENSIONS
from app.schemas.base_csi import (
    BaseCSIRegister, BaseCSIResponse, BaseCSIListResponse, BaseCSIUpdate
)
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _process_base_csi_background(base_csi_id: uuid.UUID):
    db = SessionLocal()
    try:
        BaseCSIService.process_base_csi_registration(db, base_csi_id)
    finally:
        db.close()


def _validate_base_csi_upload(file_name: Optional[str], file_size: int) -> None:
    if not file_name:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="ファイル名が必要です",
        )

    extension = Path(file_name).suffix.lower()
    if extension not in SUPPORTED_CSI_EXTENSIONS:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                "未対応のファイル形式です。"
                f"対応形式: {', '.join(sorted(SUPPORTED_CSI_EXTENSIONS))}"
            ),
        )

    if extension == ".csi":
        if not settings.PICOSCENES_ENABLED:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="PicoScenes .csi の受付は現在無効化されています",
            )
        max_bytes = settings.PICOSCENES_MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    "PicoScenes .csi ファイルが大きすぎます。"
                    f"上限: {settings.PICOSCENES_MAX_FILE_SIZE_MB}MB"
                ),
            )


@router.post("/register", response_model=BaseCSIResponse)
async def register_base_csi(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CSIファイル（.pcap / .pcapng / .cap / .csi / .csv）"),
    db: Session = Depends(get_db)
):
    """
    ベースCSIを登録（認証不要）

    .pcap / .pcapng / .cap（CSIKit）または .csi / .csv（PicoScenes）ファイルを受け付けます。
    拡張子に応じて自動的に適切なパーサーで解析し、ベースCSIとして登録します。
    """
    try:
        file_data = await file.read()

        if len(file_data) == 0:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="アップロードファイルが空です"
            )

        _validate_base_csi_upload(file.filename, len(file_data))

        register_info = BaseCSIRegister(name=file.filename or "base_csi")

        base_csi = BaseCSIService.create_base_csi_record(
            db=db,
            pcap_file_data=file_data,
            pcap_filename=file.filename or "base_csi",
            register_info=register_info
        )
        background_tasks.add_task(_process_base_csi_background, base_csi.id)

        return BaseCSIResponse(**base_csi.to_dict())

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Base CSI registration failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ベースCSI登録に失敗しました: {str(e)}"
        )


@router.get("/", response_model=BaseCSIListResponse)
async def list_base_csis(
    include_expired: bool = False,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """
    ベースCSI一覧取得

    現在のユーザーが登録したベースCSIの一覧を取得します。
    """
    try:
        base_csis, total_count = BaseCSIService.get_base_csi_list(
            db=db,
            include_expired=include_expired,
            status=None,
            page=page,
            page_size=page_size
        )

        # レスポンス構築
        base_csi_responses = [BaseCSIResponse(**bc.to_dict()) for bc in base_csis]

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

        return BaseCSIListResponse(
            base_csis=base_csi_responses,
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )

    except Exception as e:
        logger.error(f"Failed to list base CSIs: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ベースCSI一覧取得に失敗しました: {str(e)}"
        )


@router.get("/{base_csi_id}", response_model=BaseCSIResponse)
async def get_base_csi(
    base_csi_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """
    特定のベースCSIを取得
    """
    base_csi = BaseCSIService.get_base_csi_by_id(
        db=db,
        base_csi_id=base_csi_id,
    )

    if base_csi is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="ベースCSIが見つかりません"
        )

    return BaseCSIResponse(**base_csi.to_dict())


@router.put("/{base_csi_id}", response_model=BaseCSIResponse)
async def update_base_csi(
    base_csi_id: uuid.UUID,
    update_info: BaseCSIUpdate,
    db: Session = Depends(get_db)
):
    """
    ベースCSI情報を更新
    """
    base_csi = BaseCSIService.update_base_csi(
        db=db,
        base_csi_id=base_csi_id,
        update_info=update_info
    )

    if base_csi is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="ベースCSIが見つかりません"
        )

    return BaseCSIResponse(**base_csi.to_dict())


@router.delete("/{base_csi_id}")
async def delete_base_csi(
    base_csi_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """
    ベースCSIを削除
    """
    success = BaseCSIService.delete_base_csi(
        db=db,
        base_csi_id=base_csi_id
    )

    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="ベースCSIが見つかりません"
        )

    return {"message": "ベースCSIが正常に削除されました"}


@router.post("/cleanup-expired")
async def cleanup_expired_base_csis(
    db: Session = Depends(get_db)
):
    """
    有効期限切れのベースCSIを削除（管理者のみ）
    """

    count = BaseCSIService.cleanup_expired_base_csis(db)

    return {"message": f"{count}件の有効期限切れベースCSIを削除しました", "count": count}
