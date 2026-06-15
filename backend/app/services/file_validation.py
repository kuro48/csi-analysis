"""
CSIファイルアップロードの共通バリデーション
"""

from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status as http_status

from app.core.config import settings
from app.services.pcap_analyzer_pipeline import SUPPORTED_CSI_EXTENSIONS


def validate_csi_upload(
    file_name: Optional[str],
    file_size: int,
    *,
    check_picoscenes: bool = True,
) -> str:
    """アップロードCSIファイルを検証し、正規化した拡張子を返す。

    Args:
        file_name: アップロードファイル名
        file_size: ファイルサイズ（バイト）
        check_picoscenes: True のとき .csi ファイルの PICOSCENES 設定と
                          サイズ制限を追加検証する

    Returns:
        正規化した拡張子（例: ".pcap"）

    Raises:
        HTTPException 400: バリデーション失敗時
    """
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

    if check_picoscenes and extension == ".csi":
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

    return extension
