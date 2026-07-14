"""
呼吸解析エンドポイント（5-1.ipynb パイプライン専用）

CSIファイルを受け取り、breathing_pipeline（5-1.ipynb 移植）を実行して
呼吸波形の配列だけを返す。DB保存・ZKP証明生成・キャッシュは行わない
ステートレスなエンドポイントのため、複数ユーザーの同時解析に対応する。
"""

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import status as http_status
from fastapi.concurrency import run_in_threadpool

from app.services.breathing_certificate_service import BreathingCertificateService
from app.services.breathing_pipeline import run_breathing_pipeline
from app.services.verifiable_breathing_service import VerifiableBreathingService

router = APIRouter()
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSION = ".csi"

# 証明書検証サービス（回路セットアップ確認を1回だけ行う遅延シングルトン）
_certificate_service: Optional[BreathingCertificateService] = None
_verifiable_service: Optional[VerifiableBreathingService] = None


def _get_certificate_service() -> BreathingCertificateService:
    global _certificate_service
    if _certificate_service is None:
        _certificate_service = BreathingCertificateService()
    return _certificate_service


def _get_verifiable_service() -> VerifiableBreathingService:
    global _verifiable_service
    if _verifiable_service is None:
        _verifiable_service = VerifiableBreathingService()
    return _verifiable_service


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


@router.post("/analyze-certificate", response_model=Dict[str, Any])
async def analyze_breathing_certificate(
    file: UploadFile = File(..., description="PicoScenes .csi ファイル"),
) -> Dict[str, Any]:
    """CSIファイルに 5-1.ipynb パイプラインを適用し、証明書検証方式（案A）の
    ZKP 証明を生成して返す。

    既存の /analyze（波形のみ）とは別系統。回路 csi_breathing_certificate は
    再構成性 Σ_k modes ≈ vmdInput を強制するため、証明者が都合のよい VMD モードを
    捏造する余地を狭める。

    返り値:
        {
          "isNormal": bool,              # 正常帯域内 かつ 狭帯域
          "breathing_rate_bpm": float,
          "peak_freq_hz": float,
          "selected_vmd_mode": int,
          "proof": {...},                # Groth16 証明
          "publicSignals": [...],
          "diagnostics": {...},          # 再構成誤差比・narrowband比 等
        }
    """
    file_data = await file.read()
    _validate_upload(file.filename, len(file_data))

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=SUPPORTED_EXTENSION, delete=False) as tmp:
            tmp.write(file_data)
            tmp_path = Path(tmp.name)

        # CPUバウンドな解析をスレッドプールで実行
        result = await run_in_threadpool(run_breathing_pipeline, str(tmp_path))
        cert_input = result["certificate_input"]

        service = _get_certificate_service()
        proof_result = await service.generate_proof(
            vmd_input=cert_input["vmdInput"],
            modes=cert_input["modes"],
            sel=cert_input["sel"],
        )

        return {
            "isNormal": proof_result["isNormal"],
            "isValid": proof_result["isValid"],
            "breathing_rate_bpm": result["breathing_rate_bpm"],
            "peak_freq_hz": result["peak_freq_hz"],
            "selected_vmd_mode": result["selected_vmd_mode"],
            "proof": proof_result["proof"],
            "publicSignals": proof_result["publicSignals"],
            "method": proof_result["method"],
            "diagnostics": cert_input["diagnostics"],
        }
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FileNotFoundError as e:
        logger.error("Certificate circuit not set up: %s", e)
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except RuntimeError as e:
        logger.error("Certificate analysis unavailable: %s", e)
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Breathing certificate analysis failed")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"証明書解析に失敗しました: {e}",
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


@router.post("/analyze-verifiable", response_model=Dict[str, Any])
async def analyze_breathing_verifiable(
    file: UploadFile = File(..., description="PicoScenes .csi ファイル"),
) -> Dict[str, Any]:
    """5-1 解析後、Python+Circom と RISC Zero zkVM の2系統を並列実行する。"""
    file_data = await file.read()
    _validate_upload(file.filename, len(file_data))

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=SUPPORTED_EXTENSION, delete=False) as tmp:
            tmp.write(file_data)
            tmp_path = Path(tmp.name)
        return await _get_verifiable_service().analyze(str(tmp_path))
    except ValueError as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("Verifiable breathing analysis unavailable: %s", exc)
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Verifiable breathing analysis failed")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"検証可能な呼吸解析に失敗しました: {exc}",
        ) from exc
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
