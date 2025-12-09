"""
CSIデータ関連エンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException, status as http_status, File, UploadFile, Form, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
import math
import json
from datetime import datetime

from app.core.database import get_db
from app.core.deps import get_current_user, get_device_auth
from app.core.config import settings
from app.models.user import User
from app.models.device import Device
from app.services.csi_data import CSIDataService, SessionService
from app.schemas.csi_data import (
    CSIDataUpload, CSIDataResponse, CSIDataListResponse, CSIDataFilter,
    SessionCreate, SessionUpdate, SessionResponse, ProcessingStatus
)

router = APIRouter()


@router.post("/upload", response_model=CSIDataResponse)
async def upload_csi_data(
    # device_id: str = Form(..., description="デバイスID"),
    session_id: Optional[str] = Form(None, description="セッションID"),
    collection_start_time: Optional[str] = Form(None, description="収集開始時刻"),
    collection_duration: Optional[float] = Form(None, description="収集時間（秒）"),
    metadata: Optional[str] = Form(None, description="メタデータ（JSON文字列）"),
    file: UploadFile = File(..., description="CSIデータファイル"),
    db: Session = Depends(get_db)
):
    """
    CSIデータアップロード（認証なし - 研究用）
    """
    try:
        # ファイルデータ読み取り
        file_data = await file.read()

        if len(file_data) == 0:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="アップロードファイルが空です"
            )

        # アップロード情報構築
        upload_info = CSIDataUpload(
            file_name=file.filename,
            session_id=session_id,
            collection_start_time=datetime.fromisoformat(collection_start_time.replace('Z', '+00:00')) if collection_start_time else None,
            collection_duration=collection_duration,
            metadata=json.loads(metadata) if metadata else {}
        )

        # デバイスの存在確認（オプション）
        # device = db.query(Device).filter(Device.device_id == device_id).first()

        # CSIデータアップロード
        csi_data = await CSIDataService.upload_csi_data(
            db=db,
            file_data=file_data,
            upload_info=upload_info,
            user_id= None
        )

        return CSIDataResponse(
            id=csi_data.id,
            # device_id=device_id,
            session_id=csi_data.session_id,
            file_path=csi_data.file_path,
            file_size=csi_data.file_size,
            status=csi_data.status,
            ipfs_hash=csi_data.ipfs_hash,
            created_at=csi_data.created_at,
            updated_at=csi_data.updated_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CSIデータアップロードに失敗しました: {str(e)}"
        )


@router.post("/upload-test", response_model=CSIDataResponse)
async def upload_csi_data_test(
    device_id: str = Form(..., description="デバイスID"),
    session_id: Optional[str] = Form(None, description="セッションID"),
    collection_start_time: Optional[str] = Form(None, description="収集開始時刻"),
    collection_duration: Optional[float] = Form(None, description="収集時間（秒）"),
    metadata: Optional[str] = Form(None, description="メタデータ（JSON文字列）"),
    file: UploadFile = File(..., description="CSIデータファイル"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    CSIデータアップロード（テスト用・ユーザー認証）

    注意: このエンドポイントはテスト/開発環境専用です。
    本番環境では ENABLE_TEST_ENDPOINTS=False に設定して無効化してください。
    """
    # 本番環境ではテストエンドポイントを無効化
    if not settings.ENABLE_TEST_ENDPOINTS:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="このエンドポイントは本番環境では利用できません"
        )
    try:
        # ファイルデータ読み取り
        file_data = await file.read()

        if len(file_data) == 0:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="アップロードファイルが空です"
            )

        # アップロード情報構築
        upload_info = CSIDataUpload(
            file_name=file.filename or "unknown",
            session_id=session_id,
            collection_start_time=datetime.fromisoformat(collection_start_time.replace('Z', '+00:00')) if collection_start_time else None,
            collection_duration=collection_duration,
            metadata=json.loads(metadata) if metadata else {}
        )

        # CSIデータアップロード
        csi_data = await CSIDataService.upload_csi_data(
            db=db,
            device_id=device_id,
            file_data=file_data,
            upload_info=upload_info,
            user_id=current_user.id
        )

        return CSIDataResponse(
            id=csi_data.id,
            device_id=device_id,
            session_id=csi_data.session_id,
            file_path=csi_data.file_path,
            file_size=csi_data.file_size,
            status=csi_data.status,
            ipfs_hash=csi_data.ipfs_hash,
            created_at=csi_data.created_at,
            updated_at=csi_data.updated_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CSIデータアップロードに失敗しました: {str(e)}"
        )


@router.get("/", response_model=CSIDataListResponse)
async def list_csi_data(
    device_id: Optional[str] = Query(None, description="デバイスIDフィルター"),
    session_id: Optional[str] = Query(None, description="セッションIDフィルター"),
    data_status: Optional[str] = Query("all", description="ステータスフィルター"),
    start_date: Optional[str] = Query(None, description="開始日時"),
    end_date: Optional[str] = Query(None, description="終了日時"),
    page: int = Query(1, ge=1, description="ページ番号"),
    page_size: int = Query(20, ge=1, le=100, description="1ページあたりの件数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    CSIデータ一覧取得
    """
    try:
        # フィルター構築
        filters = CSIDataFilter(
            device_id=device_id,
            session_id=session_id,
            status=data_status,
            start_date=datetime.fromisoformat(start_date) if start_date else None,
            end_date=datetime.fromisoformat(end_date) if end_date else None
        )

        csi_data_list, total_count = CSIDataService.get_csi_data_list(
            db, current_user.id, filters, page, page_size
        )

        # レスポンス構築
        csi_responses = []
        for csi_data in csi_data_list:
            device = csi_data.device

            # JSONフィールドをパース（文字列の場合）
            raw_data = csi_data.raw_data
            if isinstance(raw_data, str):
                raw_data = json.loads(raw_data) if raw_data else None

            processed_data = csi_data.processed_data
            if isinstance(processed_data, str):
                processed_data = json.loads(processed_data) if processed_data else None

            csi_response = CSIDataResponse(
                id=csi_data.id,
                device_id=device.device_id if device else "unknown",
                session_id=csi_data.session_id,
                raw_data=raw_data,
                processed_data=processed_data,
                file_path=csi_data.file_path,
                file_size=csi_data.file_size,
                status=csi_data.status,
                created_at=csi_data.created_at,
                updated_at=csi_data.updated_at
            )
            csi_responses.append(csi_response)

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

        return CSIDataListResponse(
            csi_data=csi_responses,
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CSIデータ一覧取得に失敗しました: {str(e)}"
        )


@router.get("/{csi_data_id}", response_model=CSIDataResponse)
async def get_csi_data(
    csi_data_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    特定CSIデータ取得
    """
    csi_data = CSIDataService.get_csi_data_by_id(db, csi_data_id, current_user.id)
    if not csi_data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="CSIデータが見つかりません"
        )

    device = csi_data.device

    # JSONフィールドをパース（文字列の場合）
    raw_data = csi_data.raw_data
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data) if raw_data else None

    processed_data = csi_data.processed_data
    if isinstance(processed_data, str):
        processed_data = json.loads(processed_data) if processed_data else None

    return CSIDataResponse(
        id=csi_data.id,
        device_id=device.device_id if device else "unknown",
        session_id=csi_data.session_id,
        raw_data=raw_data,
        processed_data=processed_data,
        file_path=csi_data.file_path,
        file_size=csi_data.file_size,
        status=csi_data.status,
        created_at=csi_data.created_at,
        updated_at=csi_data.updated_at
    )


@router.delete("/{csi_data_id}")
async def delete_csi_data(
    csi_data_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    CSIデータ削除
    """
    success = await CSIDataService.delete_csi_data(db, csi_data_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="CSIデータが見つかりません"
        )

    return {"message": "CSIデータが正常に削除されました"}


@router.get("/{device_id}/stats")
async def get_device_csi_stats(
    device_id: str,
    days: int = Query(7, ge=1, le=365, description="統計期間（日数）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    デバイスのCSI統計情報取得
    """
    stats = CSIDataService.get_device_csi_stats(db, device_id, current_user.id, days)
    if not stats:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="デバイスが見つかりません"
        )

    return stats


@router.get("/{csi_data_id}/visualization")
async def get_csi_visualization_data(
    csi_data_id: uuid.UUID,
    subcarrier_limit: int = Query(10, ge=1, le=64, description="表示するサブキャリア数"),
    time_window: Optional[int] = Query(None, ge=1, description="時間窓（秒）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    CSIデータの可視化用データ取得
    """
    csi_data = CSIDataService.get_csi_data_by_id(db, csi_data_id, current_user.id)
    if not csi_data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="CSIデータが見つかりません"
        )

    if not csi_data.processed_data:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="CSIデータが処理されていません"
        )

    try:
        # 時系列データを取得
        time_series = csi_data.processed_data.get('subcarrier_data', {})

        # サブキャリアデータを制限
        limited_subcarriers = {}
        subcarrier_keys = list(time_series.keys())[:subcarrier_limit]

        for key in subcarrier_keys:
            sc_data = time_series[key]
            timestamps = sc_data.get('timestamps', [])
            amplitudes = sc_data.get('amplitudes', [])
            phases = sc_data.get('phases', [])

            # 時間窓の適用
            if time_window and timestamps:
                max_time = max(timestamps)
                min_time = max_time - time_window

                filtered_data = [(t, a, p) for t, a, p in zip(timestamps, amplitudes, phases)
                               if t >= min_time]

                if filtered_data:
                    timestamps, amplitudes, phases = zip(*filtered_data)
                    timestamps = list(timestamps)
                    amplitudes = list(amplitudes)
                    phases = list(phases)

            limited_subcarriers[key] = {
                'timestamps': timestamps,
                'amplitudes': amplitudes,
                'phases': phases
            }

        # 統計データ
        summary_stats = csi_data.processed_data.get('summary_stats', {})

        return {
            "csi_data_id": str(csi_data_id),
            "subcarrier_data": limited_subcarriers,
            "summary": summary_stats,
            "metadata": {
                "total_subcarriers": len(time_series),
                "displayed_subcarriers": len(limited_subcarriers),
                "time_window_applied": time_window is not None,
                "device_id": csi_data.device.device_id if csi_data.device else "unknown"
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"可視化データの生成に失敗しました: {str(e)}"
        )