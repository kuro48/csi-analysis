"""
CSIデータ関連エンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException, status as http_status, File, UploadFile, Form, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
import math
import json
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd

from app.core.database import get_db
from app.core.config import settings
from app.models.csi_data import CSIData
from app.models.base_csi import BaseCSI
from app.services.csi_data import CSIDataService, SessionService
from app.services.pcap_analyzer import PCAPAnalyzer
from app.services.zkp_service import ZKPService
from app.services.base_csi import BaseCSIService
from app.services.blockchain_service import BlockchainService
from app.api.endpoints.blockchain import get_blockchain_service
from app.schemas.csi_data import (
    CSIDataUpload, CSIDataResponse, CSIDataListResponse, CSIDataFilter,
    SessionCreate, SessionUpdate, SessionResponse, ProcessingStatus
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_json_field(value) -> Optional[dict]:
    """JSONB列の値をdictに正規化（str/dict/None対応）"""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value) if value else None
    return value


def _serialize_fft_dataframe(fft_df) -> dict:
    """FFTデータフレームをJSON化できる辞書に変換"""
    if not hasattr(fft_df, "to_dict"):
        return {}

    import numpy as np

    fft_df_copy = fft_df.copy()

    # freq_interval列がInterval型の場合は文字列に変換
    if "freq_interval" in fft_df_copy.columns:
        fft_df_copy["freq_interval"] = fft_df_copy["freq_interval"].astype(str)

    # NaN, inf, -infをNoneに置き換え（JSONで有効な値に変換）
    fft_df_copy = fft_df_copy.replace([np.nan, np.inf, -np.inf], None)
    return fft_df_copy.to_dict()


async def _record_zkp_proof_on_chain(
    csi_data: CSIData,
    base_csi_comparison: dict,
    csi_data_id: uuid.UUID,
    db: Session
) -> None:
    """ZKP証明をブロックチェーンに自動記録"""
    try:
        blockchain_service = get_blockchain_service()

        if not blockchain_service.is_available():
            logger.warning(
                f"Blockchain service not available for CSI data {csi_data_id}. "
                f"Skipping automatic blockchain recording."
            )
            return

        device_id = getattr(csi_data, "device_id", None)
        if not device_id:
            logger.warning(f"CSI data {csi_data_id} has no device_id; skipping blockchain record")
            return
        zkp_proof = base_csi_comparison["zkp_proof"]
        public_signals = base_csi_comparison["public_signals"]

        proof_id = await blockchain_service.record_zkp_proof(
            device_id=device_id,
            proof=zkp_proof,
            public_signals=public_signals,
            proof_type="full_similarity"
        )

        if not proof_id:
            logger.warning(
                f"Failed to record ZKP proof on blockchain for CSI data {csi_data_id}"
            )
            return

        logger.info(
            f"ZKP proof automatically recorded on blockchain: "
            f"CSI data {csi_data_id}, proof ID {proof_id}"
        )

        # 任意タイミングでの verify-proof-on-chain 呼び出しに備えて証明データを DB に保持
        csi_data.processed_data["blockchain_proof_id"] = proof_id
        csi_data.processed_data["blockchain_proof_data"] = {
            "proof": zkp_proof,
            "public_signals": public_signals,
        }
        db.commit()
    except Exception as e:
        logger.warning(
            f"Failed to record ZKP proof on blockchain for CSI data {csi_data_id}: {e}",
            exc_info=True
        )


async def _run_base_csi_comparison(
    db: Session,
    analyzer: "PCAPAnalyzer",
    zkp_service: "ZKPService",
    fft_dataframe,
    base_csi_id: Optional[uuid.UUID],
    user_id: Optional[uuid.UUID],
) -> Optional[dict]:
    """
    ベースCSIとのコサイン類似度比較・ZKP証明生成

    Args:
        db: DBセッション
        analyzer: PCAPアナライザーインスタンス
        zkp_service: ZKPサービスインスタンス
        fft_dataframe: アップロードCSIのFFT DataFrame
        base_csi_id: ベースCSI ID（None の場合は最新を使用）
        user_id: ユーザーID

    Returns:
        比較結果の辞書。ベースCSIが存在しない場合は None。
    """
    if base_csi_id:
        base_csi = BaseCSIService.get_base_csi_by_id(db, base_csi_id, user_id=None)
    else:
        base_csis, _ = BaseCSIService.get_base_csi_list(
            db=db, user_id=None, include_expired=False, page=1, page_size=1
        )
        base_csi = base_csis[0] if base_csis else None

    if not base_csi:
        logger.warning("No base CSI found for comparison")
        return None

    logger.info(f"Comparing with base CSI: {base_csi.id} ({base_csi.name})")

    base_fft_df = pd.DataFrame(base_csi.fft_dataframe)
    extract_kwargs = dict(freq_col='freq_interval', use_binned=True,
                         freq_min=analyzer.ZKP_FREQ_START, freq_max=analyzer.ZKP_FREQ_END)

    base_data = analyzer.extract_full_subcarrier_vectors(base_fft_df, **extract_kwargs)
    upload_data = analyzer.extract_full_subcarrier_vectors(fft_dataframe, **extract_kwargs)
    reference_matrix = base_data["csi_matrix"]
    candidate_matrix = upload_data["csi_matrix"]

    similarity_result = await zkp_service.generate_proof(
        reference_matrix=reference_matrix,
        candidate_matrix=candidate_matrix
    )
    python_similarity = zkp_service.compute_python_similarity(
        reference_matrix=reference_matrix,
        candidate_matrix=candidate_matrix
    )
    python_top_n_result = zkp_service.select_top_n_subcarriers(
        reference_matrix=reference_matrix,
        candidate_matrix=candidate_matrix,
        top_n=5
    )
    zkp_top_n_result = zkp_service.extract_top_n_from_similarities(
        zkp_similarities=similarity_result.get("similarities", []),
        scale=10000,
        top_n=5
    )

    logger.info(
        f"Base CSI comparison completed: similarity={similarity_result['normalizedSimilarity']:.4f}, "
        f"dimensions={base_data['num_freq_points']}×{base_data['num_subcarriers']}"
    )

    subcarrier_entry = lambda indices, sims: [
        {"index": idx, "similarity": sim, "rank": i + 1}
        for i, (idx, sim) in enumerate(zip(indices, sims))
    ]

    return {
        "base_csi_id": str(base_csi.id),
        "base_csi_name": base_csi.name,
        "similarity_score": similarity_result["normalizedSimilarity"],
        "zkp_proof": similarity_result.get("proof", {}),
        "public_signals": similarity_result.get("publicSignals", []),
        "is_valid": similarity_result.get("isValid", False),
        "python_similarity": python_similarity.get("cosine_similarity"),
        "selected_subcarrier": {
            "index": similarity_result.get("selectedSubcarrierIndex"),
            "similarity": similarity_result.get("selectedSubcarrierSimilarity"),
        },
        "lowest_similarity_subcarrier": {  # 後方互換
            "index": similarity_result.get("selectedSubcarrierIndex"),
            "similarity": similarity_result.get("selectedSubcarrierSimilarity"),
        },
        "zkp_top_5_lowest_subcarriers": subcarrier_entry(
            zkp_top_n_result["top_n_indices"], zkp_top_n_result["top_n_similarities"]
        ),
        "python_top_5_lowest_subcarriers": subcarrier_entry(
            python_top_n_result["top_n_indices"], python_top_n_result["top_n_similarities"]
        ),
        "data_dimensions": {
            "num_freq_points": base_data["num_freq_points"],
            "num_subcarriers": base_data["num_subcarriers"],
            "total_dimensions": base_data["num_freq_points"] * base_data["num_subcarriers"],
        },
    }


async def _process_and_generate_zkp_background(
    csi_data_id: uuid.UUID,
    file_path: str,
    db_session_maker,
    user_id: Optional[uuid.UUID] = None,
    base_csi_id: Optional[uuid.UUID] = None
):
    """
    バックグラウンドでPCAP解析・ZKP証明生成・DB保存・ブロックチェーン記録を実行

    Args:
        csi_data_id: CSIデータID
        file_path: PCAPファイルパス
        db_session_maker: データベースセッションファクトリ
        user_id: ユーザーID（ベースCSI比較用）
        base_csi_id: ベースCSI ID（指定されない場合は最新のアクティブなベースCSIを使用）
    """
    db = None
    try:
        db = db_session_maker()
        logger.info(f"Starting background processing for CSI data {csi_data_id}")

        csi_data = db.query(CSIData).filter_by(id=csi_data_id).first()
        if csi_data:
            csi_data.status = "processing"
            db.commit()

        analyzer = PCAPAnalyzer()
        zkp_service = ZKPService(auto_compile=settings.ZKP_AUTO_COMPILE)

        # --- PCAP解析（FFT + ウェーブレット変換） ---
        logger.info(f"Analyzing PCAP file: {file_path}")
        analysis_result = analyzer.analyze_pcap_file(file_path)
        binned_fft_df = analysis_result["fft"]
        binned_wavelet_df = analysis_result["wavelet"]
        if binned_fft_df.empty:
            raise ValueError("PCAP解析に失敗しました: データが空です")

        # --- ベースCSI比較・ZKP証明生成 ---
        base_csi_comparison = None
        try:
            base_csi_comparison = await _run_base_csi_comparison(
                db=db,
                analyzer=analyzer,
                zkp_service=zkp_service,
                fft_dataframe=binned_fft_df,
                base_csi_id=base_csi_id,
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(f"Base CSI comparison failed: {e}", exc_info=True)

        # --- DB保存 ---
        if csi_data:
            csi_data.status = "completed"
            processed_data: dict = {
                "fft_dataframe": _serialize_fft_dataframe(binned_fft_df),
                "wavelet_dataframe": _serialize_fft_dataframe(binned_wavelet_df),
                "breathing_rate_comparison": {
                    "fft_bpm": analysis_result["breathing_rate_fft_bpm"],
                    "wavelet_bpm": analysis_result["breathing_rate_wavelet_bpm"],
                },
            }
            if base_csi_comparison:
                processed_data["base_csi_comparison"] = base_csi_comparison
            csi_data.processed_data = processed_data
            db.commit()

            # --- ブロックチェーン記録 ---
            if base_csi_comparison:
                await _record_zkp_proof_on_chain(
                    csi_data=csi_data,
                    base_csi_comparison=base_csi_comparison,
                    csi_data_id=csi_data_id,
                    db=db,
                )

            if base_csi_comparison:
                logger.info(
                    f"Background processing completed for CSI data {csi_data_id}: "
                    f"similarity={base_csi_comparison['similarity_score']:.4f}"
                )
            else:
                logger.info(f"Background processing completed for CSI data {csi_data_id}")

    except ValueError as e:
        logger.error(f"Validation error in background processing for CSI data {csi_data_id}: {e}", exc_info=True)
        if db and csi_data:
            csi_data.status = "error"
            csi_data.processed_data = {
                "error": str(e),
                "error_type": "ValidationError",
                "error_category": "pcap_analysis_failed",
            }
            db.commit()

    except Exception as e:
        logger.error(f"Background processing failed for CSI data {csi_data_id}: {e}", exc_info=True)
        if db and csi_data:
            csi_data.status = "error"
            csi_data.processed_data = {
                "error": str(e),
                "error_type": type(e).__name__,
                "error_category": "processing_failed",
            }
            db.commit()

    finally:
        if db:
            db.close()

@router.post("/upload", response_model=CSIDataResponse)
async def upload_csi_data(
    background_tasks: BackgroundTasks,
    session_id: Optional[str] = Form(None, description="セッションID"),
    collection_start_time: Optional[str] = Form(None, description="収集開始時刻"),
    collection_duration: Optional[float] = Form(None, description="収集時間（秒）"),
    metadata: Optional[str] = Form(None, description="メタデータ（JSON文字列）"),
    file: UploadFile = File(..., description="CSIデータファイル"),
    db: Session = Depends(get_db)
):
    """
    CSIデータアップロード（認証なし - 研究用）

    アップロード後、自動的にPCAP解析とZKP証明生成を実行します。
    処理はバックグラウンドで実行されるため、アップロードレスポンスは即座に返されます。
    処理状態は status フィールドで確認できます:
    - "uploaded": アップロード完了、処理待機中
    - "processing": PCAP解析中
    - "completed": 解析とZKP証明生成完了
    - "error": エラー発生
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

        # CSIデータアップロード
        csi_data = await CSIDataService.upload_csi_data(
            db=db,
            file_data=file_data,
            upload_info=upload_info
        )

        # バックグラウンドタスクでPCAP解析+ZKP証明生成を実行
        from app.core.database import SessionLocal
        background_tasks.add_task(
            _process_and_generate_zkp_background,
            csi_data_id=csi_data.id,
            file_path=csi_data.file_path,
            db_session_maker=SessionLocal
        )

        logger.info(f"CSI data uploaded: {csi_data.id}, background processing scheduled")

        return CSIDataResponse(
            id=csi_data.id,
            session_id=csi_data.session_id,
            device_id=csi_data.device_id,
            file_path=csi_data.file_path,
            file_size=csi_data.file_size,
            status=csi_data.status,
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
    session_id: Optional[str] = Query(None, description="セッションIDフィルター"),
    data_status: Optional[str] = Query("all", description="ステータスフィルター"),
    start_date: Optional[str] = Query(None, description="開始日時"),
    end_date: Optional[str] = Query(None, description="終了日時"),
    page: int = Query(1, ge=1, description="ページ番号"),
    page_size: int = Query(20, ge=1, le=100, description="1ページあたりの件数"),
    db: Session = Depends(get_db)
):
    """
    CSIデータ一覧取得
    """
    try:
        # フィルター構築
        filters = CSIDataFilter(
            session_id=session_id,
            status=data_status,
            start_date=datetime.fromisoformat(start_date) if start_date else None,
            end_date=datetime.fromisoformat(end_date) if end_date else None
        )

        csi_data_list, total_count = CSIDataService.get_csi_data_list(
            db, filters, page, page_size
        )

        # レスポンス構築
        csi_responses = []
        for csi_data in csi_data_list:
            csi_response = CSIDataResponse(
                id=csi_data.id,
                session_id=csi_data.session_id,
                raw_data=_parse_json_field(csi_data.raw_data),
                processed_data=_parse_json_field(csi_data.processed_data),
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
    db: Session = Depends(get_db)
):
    """
    特定CSIデータ取得
    """
    csi_data = CSIDataService.get_csi_data_by_id(db, csi_data_id)
    if not csi_data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="CSIデータが見つかりません"
        )

    return CSIDataResponse(
        id=csi_data.id,
        session_id=csi_data.session_id,
        raw_data=_parse_json_field(csi_data.raw_data),
        processed_data=_parse_json_field(csi_data.processed_data),
        file_path=csi_data.file_path,
        file_size=csi_data.file_size,
        status=csi_data.status,
        created_at=csi_data.created_at,
        updated_at=csi_data.updated_at
    )


@router.delete("/{csi_data_id}")
async def delete_csi_data(
    csi_data_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """
    CSIデータ削除
    """
    success = await CSIDataService.delete_csi_data(db, csi_data_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="CSIデータが見つかりません"
        )

    return {"message": "CSIデータが正常に削除されました"}

@router.get("/{csi_data_id}/visualization")
async def get_csi_visualization_data(
    csi_data_id: uuid.UUID,
    subcarrier_limit: int = Query(10, ge=1, le=64, description="表示するサブキャリア数"),
    time_window: Optional[int] = Query(None, ge=1, description="時間窓（秒）"),
    db: Session = Depends(get_db)
):
    """
    CSIデータの可視化用データ取得
    """
    csi_data = CSIDataService.get_csi_data_by_id(db, csi_data_id)
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
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"可視化データの生成に失敗しました: {str(e)}"
        )
