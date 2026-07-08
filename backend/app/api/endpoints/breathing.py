"""
呼吸解析エンドポイント（5-1.ipynb パイプライン専用）

CSIファイルを受け取り、breathing_pipeline（5-1.ipynb 移植）を実行して
呼吸波形の配列だけを返す。DB保存・ZKP証明生成・キャッシュは行わない
ステートレスなエンドポイントのため、複数ユーザーの同時解析に対応する。
"""

import logging
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import status as http_status
from fastapi.concurrency import run_in_threadpool

from app.services.breathing_pipeline import run_breathing_pipeline

router = APIRouter()
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSION = ".csi"


def _validate_upload(filename: Optional[str], file_size: int) -> None:
    if not filename or Path(filename).suffix.lower() != SUPPORTED_EXTENSION:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"未対応のファイル形式です。対応形式: {SUPPORTED_EXTENSION}（PicoScenes CSI）",
        )
    if file_size == 0:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="アップロードファイルが空です",
        )


@router.post("/analyze", response_model=List[float])
async def analyze_breathing(
    file: UploadFile = File(..., description="PicoScenes .csi ファイル"),
) -> List[float]:
    """CSIファイルに 5-1.ipynb の解析を適用し、呼吸波形の配列のみを返す。

    返り値は VMD で分解された呼吸成分の時系列（サンプリング 100Hz）。
    ウェーブレット・MUSIC・ZKP証明生成・DB保存は行わない。
    """
    file_data = await file.read()
    _validate_upload(file.filename, len(file_data))

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=SUPPORTED_EXTENSION, delete=False) as tmp:
            tmp.write(file_data)
            tmp_path = Path(tmp.name)

        # CPUバウンドな解析をスレッドプールで実行し、他リクエストをブロックしない
        result = await run_in_threadpool(run_breathing_pipeline, str(tmp_path))
        return result["respiration_waveform"]
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        logger.error("Breathing analysis unavailable: %s", e)
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Breathing analysis failed")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"呼吸解析に失敗しました: {e}",
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
