"""
CSIデータバックグラウンド処理サービス

解析・ZKP証明生成・DB保存のオーケストレーションを
エンドポイント層から分離する。
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.models.csi_data import CSIData
from app.services.verifiable_breathing_service import VerifiableBreathingService, attach_bpm_evaluation

logger = logging.getLogger(__name__)

# CSI parsing and proof generation are memory-heavy.  BackgroundTasks can run
# once per upload, so without a guard a second upload starts another full
# matrix/prover in the same backend process and can make the container exit.
_CSI_PROCESSING_SEMAPHORE = asyncio.Semaphore(1)


def parse_json_field(value) -> Optional[dict]:
    """JSONB列の値をdictに正規化（str/dict/None対応）。"""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value) if value else None
    return value


async def process_csi_in_background(
    csi_data_id: uuid.UUID,
    file_path: str,
    db_session_maker,
    user_id: Optional[uuid.UUID] = None,
    base_csi_id: Optional[uuid.UUID] = None,
) -> None:
    """バックグラウンドでCSI解析・ZKP証明生成・DB保存・ブロックチェーン記録を実行する。

    ファイル形式（.pcap / .csi など）は拡張子から自動判定する。
    """
    if _CSI_PROCESSING_SEMAPHORE.locked():
        logger.info("CSI data %s is queued behind another analysis", csi_data_id)

    await _CSI_PROCESSING_SEMAPHORE.acquire()
    db = None
    csi_data = None
    try:
        db = db_session_maker()
        logger.info(f"Starting background processing for CSI data {csi_data_id}")

        csi_data = db.query(CSIData).filter_by(id=csi_data_id).first()
        if csi_data:
            csi_data.status = "processing"
            await asyncio.to_thread(db.commit)

        # 解析経路は 5-1.ipynb 由来の Python 解析と Lomb--Scargle、および各 Circom 証明。
        verifiable_result = await VerifiableBreathingService().analyze(file_path)
        if csi_data and callable(getattr(db, "refresh", None)):
            # 解析中にWeb画面から正解BPMが入力された場合も最新値を取り込む。
            await asyncio.to_thread(db.refresh, csi_data)
        ground_truth_bpm = getattr(csi_data, "ground_truth_bpm", None) if csi_data else None
        if ground_truth_bpm is not None:
            attach_bpm_evaluation(verifiable_result, ground_truth_bpm)
        if csi_data:
            csi_data.status = "completed"
            csi_data.processed_data = verifiable_result
            await asyncio.to_thread(db.commit)
        logger.info(
            "5-1 verifiable processing completed for CSI data %s: status=%s",
            csi_data_id,
            verifiable_result.get("status"),
        )

    except Exception as e:
        logger.error(
            f"Background processing failed for CSI data {csi_data_id}: {e}",
            exc_info=True,
        )
        if db and csi_data:
            csi_data.status = "error"
            csi_data.processed_data = {
                "error": str(e),
                "error_type": type(e).__name__,
                "error_category": "processing_failed",
            }
            await asyncio.to_thread(db.commit)

    finally:
        _CSI_PROCESSING_SEMAPHORE.release()
        if not settings.RESEARCH_MODE and file_path:
            temp_path = Path(file_path)
            if temp_path.exists():
                try:
                    temp_path.unlink()
                    logger.info(f"Temporary CSI file deleted after background processing: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary CSI file {file_path}: {e}")
            if db and csi_data:
                csi_data.file_path = None
                csi_data.file_size = None
                await asyncio.to_thread(db.commit)
        if db:
            await asyncio.to_thread(db.close)
