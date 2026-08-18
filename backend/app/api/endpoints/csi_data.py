"""
CSIデータ関連エンドポイント
"""

import json
import logging
import math
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.schemas.csi_data import (
    CSIDataFilter,
    CSIDataListResponse,
    CSIDataResponse,
    CSIDataUpload,
    GroundTruthBpmUpdate,
)
from app.services.csi_data import CSIDataService
from app.services.csi_processing import parse_json_field, process_csi_in_background
from app.services.file_validation import validate_csi_upload
from app.services.verifiable_breathing_service import attach_bpm_evaluation

router = APIRouter()
logger = logging.getLogger(__name__)

_CHUNK_TMP_DIR = Path(tempfile.gettempdir()) / "csi_data_chunks"


@router.post("/upload-chunk")
async def upload_csi_data_chunk(
    background_tasks: BackgroundTasks,
    chunk: UploadFile = File(...),
    upload_id: Optional[str] = Form(None),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    session_id: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """チャンク分割アップロード（Cloudflare 524対策）"""
    validate_csi_upload(filename, None)

    if not upload_id:
        upload_id = uuid.uuid4().hex

    session_dir = _CHUNK_TMP_DIR / upload_id
    session_dir.mkdir(parents=True, exist_ok=True)

    chunk_data = await chunk.read()
    (session_dir / f"chunk_{chunk_index:05d}").write_bytes(chunk_data)

    received = sorted(session_dir.glob("chunk_*"))
    if len(received) < total_chunks:
        return JSONResponse({"upload_id": upload_id, "chunks_received": len(received)})

    assembled_size = sum(p.stat().st_size for p in received)
    try:
        validate_csi_upload(filename, assembled_size)
    except HTTPException:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise

    assembled_path = session_dir / "assembled_upload"
    try:
        with assembled_path.open("wb") as assembled_file:
            for chunk_path in received:
                with chunk_path.open("rb") as chunk_file:
                    shutil.copyfileobj(chunk_file, assembled_file, length=1024 * 1024)

        upload_info = CSIDataUpload(
            file_name=filename,
            session_id=session_id,
            metadata=json.loads(metadata) if metadata else {},
        )
        csi_data = await CSIDataService.upload_csi_data_from_path(
            db=db,
            source_path=assembled_path,
            upload_info=upload_info,
        )
    finally:
        shutil.rmtree(session_dir, ignore_errors=True)

    background_tasks.add_task(
        process_csi_in_background,
        csi_data_id=csi_data.id,
        file_path=csi_data.file_path,
        db_session_maker=SessionLocal,
    )

    return JSONResponse(
        {
            "upload_id": upload_id,
            "chunks_received": total_chunks,
            "csi_data": {
                "id": str(csi_data.id),
                "status": csi_data.status,
                "file_size": csi_data.file_size,
                "created_at": csi_data.created_at.isoformat(),
                "updated_at": csi_data.updated_at.isoformat(),
                "session_id": csi_data.session_id,
                "device_id": csi_data.device_id,
                "ground_truth_bpm": getattr(csi_data, "ground_truth_bpm", None),
                "processed_data": csi_data.processed_data,
            },
        }
    )


@router.post("/upload", response_model=CSIDataResponse)
async def upload_csi_data(
    background_tasks: BackgroundTasks,
    session_id: Optional[str] = Form(None, description="セッションID"),
    collection_start_time: Optional[str] = Form(None, description="収集開始時刻"),
    collection_duration: Optional[float] = Form(None, description="収集時間（秒）"),
    metadata: Optional[str] = Form(None, description="メタデータ（JSON文字列）"),
    file: UploadFile = File(..., description="CSIデータファイル"),
    db: Session = Depends(get_db),
):
    """
    CSIデータアップロード（認証なし - 研究用）

    アップロード後、自動的に CSI 解析と ZKP 証明生成を実行します。
    処理はバックグラウンドで実行されるため、アップロードレスポンスは即座に返されます。
    処理状態は status フィールドで確認できます:
    - "uploaded": アップロード完了、処理待機中
    - "processing": CSI解析中
    - "completed": CSI解析とZKP証明生成完了
    - "error": エラー発生
    """
    try:
        file_data = await file.read()

        if len(file_data) == 0:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="アップロードファイルが空です",
            )

        validate_csi_upload(file.filename, len(file_data))

        upload_info = CSIDataUpload(
            file_name=file.filename,
            session_id=session_id,
            collection_start_time=(
                datetime.fromisoformat(collection_start_time.replace("Z", "+00:00")) if collection_start_time else None
            ),
            collection_duration=collection_duration,
            metadata=json.loads(metadata) if metadata else {},
        )

        csi_data = await CSIDataService.upload_csi_data(
            db=db,
            file_data=file_data,
            upload_info=upload_info,
        )

        background_tasks.add_task(
            process_csi_in_background,
            csi_data_id=csi_data.id,
            file_path=csi_data.file_path,
            db_session_maker=SessionLocal,
        )

        logger.info(f"CSI data uploaded: {csi_data.id}, background processing scheduled")

        return CSIDataResponse(
            id=csi_data.id,
            session_id=csi_data.session_id,
            device_id=csi_data.device_id,
            ground_truth_bpm=csi_data.ground_truth_bpm,
            file_path=csi_data.file_path if settings.RESEARCH_MODE else None,
            file_size=csi_data.file_size if settings.RESEARCH_MODE else None,
            status=csi_data.status,
            created_at=csi_data.created_at,
            updated_at=csi_data.updated_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CSIデータアップロードに失敗しました: {str(e)}",
        )


@router.get("/", response_model=CSIDataListResponse)
async def list_csi_data(
    session_id: Optional[str] = Query(None, description="セッションIDフィルター"),
    data_status: Optional[str] = Query("all", description="ステータスフィルター"),
    start_date: Optional[str] = Query(None, description="開始日時"),
    end_date: Optional[str] = Query(None, description="終了日時"),
    page: int = Query(1, ge=1, description="ページ番号"),
    page_size: int = Query(20, ge=1, le=100, description="1ページあたりの件数"),
    db: Session = Depends(get_db),
):
    """
    CSIデータ一覧取得
    """
    try:
        filters = CSIDataFilter(
            session_id=session_id,
            status=data_status,
            start_date=datetime.fromisoformat(start_date) if start_date else None,
            end_date=datetime.fromisoformat(end_date) if end_date else None,
        )

        csi_data_list, total_count = CSIDataService.get_csi_data_list(db, filters, page, page_size)

        csi_responses = [
            CSIDataResponse(
                id=csi_data.id,
                session_id=csi_data.session_id,
                device_id=csi_data.device_id,
                ground_truth_bpm=csi_data.ground_truth_bpm,
                raw_data=parse_json_field(csi_data.raw_data),
                processed_data=parse_json_field(csi_data.processed_data),
                file_path=csi_data.file_path,
                file_size=csi_data.file_size,
                status=csi_data.status,
                created_at=csi_data.created_at,
                updated_at=csi_data.updated_at,
            )
            for csi_data in csi_data_list
        ]

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

        return CSIDataListResponse(
            csi_data=csi_responses,
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CSIデータ一覧取得に失敗しました: {str(e)}",
        )


@router.patch("/{csi_data_id}/ground-truth", response_model=CSIDataResponse)
async def update_ground_truth_bpm(
    csi_data_id: uuid.UUID,
    payload: GroundTruthBpmUpdate,
    db: Session = Depends(get_db),
):
    """保存済みCSIへ評価用の正解BPMを後から設定・変更・削除する。"""

    csi_data = CSIDataService.get_csi_data_by_id(db, csi_data_id)
    if not csi_data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="CSIデータが見つかりません",
        )

    csi_data.ground_truth_bpm = payload.ground_truth_bpm
    processed_data = parse_json_field(csi_data.processed_data)
    if isinstance(processed_data, dict):
        processed_data = dict(processed_data)
        if payload.ground_truth_bpm is None:
            processed_data.pop("bpm_evaluation", None)
        elif processed_data.get("analysis"):
            attach_bpm_evaluation(processed_data, payload.ground_truth_bpm)
        csi_data.processed_data = processed_data

    db.commit()
    db.refresh(csi_data)
    return CSIDataResponse(
        id=csi_data.id,
        session_id=csi_data.session_id,
        device_id=csi_data.device_id,
        ground_truth_bpm=csi_data.ground_truth_bpm,
        raw_data=parse_json_field(csi_data.raw_data),
        processed_data=parse_json_field(csi_data.processed_data),
        file_path=csi_data.file_path,
        file_size=csi_data.file_size,
        status=csi_data.status,
        created_at=csi_data.created_at,
        updated_at=csi_data.updated_at,
    )


@router.get("/{csi_data_id}", response_model=CSIDataResponse)
async def get_csi_data(
    csi_data_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    特定CSIデータ取得
    """
    csi_data = CSIDataService.get_csi_data_by_id(db, csi_data_id)
    if not csi_data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="CSIデータが見つかりません",
        )

    return CSIDataResponse(
        id=csi_data.id,
        session_id=csi_data.session_id,
        device_id=csi_data.device_id,
        ground_truth_bpm=csi_data.ground_truth_bpm,
        raw_data=parse_json_field(csi_data.raw_data),
        processed_data=parse_json_field(csi_data.processed_data),
        file_path=csi_data.file_path,
        file_size=csi_data.file_size,
        status=csi_data.status,
        created_at=csi_data.created_at,
        updated_at=csi_data.updated_at,
    )


@router.delete("/{csi_data_id}")
async def delete_csi_data(
    csi_data_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    CSIデータ削除
    """
    success = await CSIDataService.delete_csi_data(db, csi_data_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="CSIデータが見つかりません",
        )

    return {"message": "CSIデータが正常に削除されました"}
