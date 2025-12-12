"""
ベースCSI管理エンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException, status as http_status, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import math
import json
import logging

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.base_csi import BaseCSIService
from app.schemas.base_csi import (
    BaseCSIRegister, BaseCSIResponse, BaseCSIListResponse, BaseCSIUpdate
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/register", response_model=BaseCSIResponse)
async def register_base_csi(
    name: str = Form(..., description="ベースCSI名"),
    description: Optional[str] = Form(None, description="説明"),
    expires_in_days: Optional[int] = Form(None, description="有効期限（日数）"),
    file: UploadFile = File(..., description="PCAPファイル"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ベースCSIを登録

    PCAPファイルから呼吸パターンを解析し、ベースCSIとして登録します。
    登録されたベースCSIは、後続のアップロードCSIと比較する際の基準として使用されます。
    """
    try:
        # ファイルデータ読み取り
        file_data = await file.read()

        if len(file_data) == 0:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="アップロードファイルが空です"
            )

        # 登録情報構築
        register_info = BaseCSIRegister(
            name=name,
            description=description,
            expires_in_days=expires_in_days
        )

        # ベースCSI登録
        base_csi = await BaseCSIService.register_base_csi(
            db=db,
            pcap_file_data=file_data,
            pcap_filename=file.filename or "unknown.pcap",
            register_info=register_info,
            user_id=current_user.id
        )

        return BaseCSIResponse(**base_csi.to_dict())

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ベースCSI一覧取得

    現在のユーザーが登録したベースCSIの一覧を取得します。
    """
    try:
        base_csis, total_count = BaseCSIService.get_base_csi_list(
            db=db,
            user_id=current_user.id,
            include_expired=include_expired,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    特定のベースCSIを取得
    """
    base_csi = BaseCSIService.get_base_csi_by_id(
        db=db,
        base_csi_id=base_csi_id,
        user_id=current_user.id
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ベースCSI情報を更新
    """
    base_csi = BaseCSIService.update_base_csi(
        db=db,
        base_csi_id=base_csi_id,
        update_info=update_info,
        user_id=current_user.id
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ベースCSIを削除
    """
    success = BaseCSIService.delete_base_csi(
        db=db,
        base_csi_id=base_csi_id,
        user_id=current_user.id
    )

    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="ベースCSIが見つかりません"
        )

    return {"message": "ベースCSIが正常に削除されました"}


@router.post("/cleanup-expired")
async def cleanup_expired_base_csis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    有効期限切れのベースCSIを削除（管理者のみ）
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="この操作には管理者権限が必要です"
        )

    count = BaseCSIService.cleanup_expired_base_csis(db)

    return {"message": f"{count}件の有効期限切れベースCSIを削除しました", "count": count}
