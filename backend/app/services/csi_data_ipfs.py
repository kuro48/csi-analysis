"""
CSIデータIPFS/ブロックチェーン統合サービス（将来の再利用用）

このファイルは将来的にIPFS/ブロックチェーン統合を再有効化する際に使用します。
現在は使用されていませんが、コードは保持されています。
"""

import uuid
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from app.services.ipfs import ipfs_service
from app.services.blockchain_service import blockchain_service

logger = logging.getLogger(__name__)


async def upload_csi_data_to_ipfs_and_blockchain(
    device_id: str,
    file_data: bytes,
    upload_info: Any,  # CSIDataUpload型
    user_id: uuid.UUID
) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """
    CSIデータをIPFS/ブロックチェーンにアップロード

    Args:
        device_id: デバイスID
        file_data: ファイルデータ
        upload_info: アップロード情報
        user_id: ユーザーID

    Returns:
        (ipfs_hash, blockchain_tx_hash, blockchain_status, metadata_hash)
    """

    # IPFSに統合アップロード（メタデータ含む）
    ipfs_hash = None
    metadata_hash = None
    try:
        # メタデータ構築
        csi_metadata = {
            "device_id": device_id,
            "session_id": upload_info.session_id,
            "collection_start_time": upload_info.collection_start_time.isoformat() if upload_info.collection_start_time else None,
            "collection_duration": upload_info.collection_duration,
            "original_filename": upload_info.file_name,
            "file_size": len(file_data),
            "upload_timestamp": datetime.now().isoformat(),
            "user_id": str(user_id),
            "custom_metadata": upload_info.metadata
        }

        # IPFS統合アップロード
        ipfs_result = await ipfs_service.upload_csi_data_with_metadata(
            file_data,
            csi_metadata,
            filename=upload_info.file_name
        )
        ipfs_hash = ipfs_result["combined_hash"]
        metadata_hash = ipfs_result["metadata_hash"]
        logger.info(f"CSI data package uploaded to IPFS: {ipfs_hash}")
    except Exception as e:
        logger.warning(f"IPFS upload failed, continuing without IPFS: {e}")

    # ブロックチェーン記録処理
    blockchain_tx_hash = None
    blockchain_status = "pending"

    if ipfs_hash and blockchain_service.enabled:
        try:
            # ブロックチェーンにCIDを記録（非同期バックグラウンド処理）
            blockchain_result = await blockchain_service.record_csi_data_cid(
                device_id=device_id,
                ipfs_cid=ipfs_hash,
                metadata_hash=metadata_hash or ipfs_hash
            )
            blockchain_tx_hash = blockchain_result["tx_hash"]
            blockchain_status = blockchain_result["status"]
            logger.info(f"CSI data CID recorded on blockchain: {blockchain_tx_hash}")
        except Exception as e:
            logger.error(f"Blockchain recording failed: {e}")
            blockchain_status = "failed"

    return ipfs_hash, blockchain_tx_hash, blockchain_status, metadata_hash


async def delete_csi_data_from_ipfs(ipfs_hash: str) -> bool:
    """
    IPFSからCSIデータパッケージを削除

    Args:
        ipfs_hash: IPFSハッシュ

    Returns:
        削除成功したかどうか
    """
    try:
        await ipfs_service.delete_csi_data_package(ipfs_hash)
        logger.info(f"CSI data package deleted from IPFS: {ipfs_hash}")
        return True
    except Exception as e:
        logger.warning(f"Failed to delete IPFS package {ipfs_hash}: {e}")
        return False
