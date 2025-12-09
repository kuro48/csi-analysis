"""
IPFS サービス - HTTP API直接実装
"""

import asyncio
import io
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple, Union

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class IPFSService:
    """IPFS クライアントサービス (HTTP API使用)"""

    def __init__(self):
        # IPFS HTTP API接続設定（Docker環境対応）
        if settings.IPFS_HOST == "ipfs":
            # Docker環境
            self._api_url = f"http://ipfs:{settings.IPFS_PORT}/api/v0"
        else:
            # ローカル環境
            self._api_url = f"http://{settings.IPFS_HOST}:{settings.IPFS_PORT}/api/v0"

        self._client = None
        logger.info(f"IPFS API URL configured: {self._api_url}")

    async def _get_http_client(self) -> httpx.AsyncClient:
        """HTTP クライアントを取得"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def upload_file(self, file_data: bytes, filename: str = None) -> str:
        """
        ファイルをIPFSにアップロード

        Args:
            file_data: アップロードするファイルのバイナリデータ
            filename: ファイル名（オプション）

        Returns:
            str: IPFSハッシュ値
        """
        try:
            client = await self._get_http_client()

            # ファイルをmultipart/form-dataとして送信
            files = {"file": (filename or "file", file_data, "application/octet-stream")}

            response = await client.post(f"{self._api_url}/add", files=files, params={"pin": "true"})
            response.raise_for_status()

            # レスポンスからハッシュ値を取得
            result = response.json()
            ipfs_hash = result["Hash"]

            logger.info(f"File uploaded to IPFS: {ipfs_hash}")
            return ipfs_hash

        except Exception as e:
            logger.error(f"IPFS upload failed: {e}")
            raise RuntimeError(f"IPFSアップロードに失敗しました: {e}")

    async def upload_json(self, data: Dict, filename: str = None) -> str:
        """
        JSONデータをIPFSにアップロード

        Args:
            data: アップロードするJSONデータ
            filename: ファイル名（オプション）

        Returns:
            str: IPFSハッシュ値
        """
        try:
            # JSONをバイナリに変換
            json_data = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            return await self.upload_file(json_data, filename or "data.json")

        except Exception as e:
            logger.error(f"IPFS JSON upload failed: {e}")
            raise RuntimeError(f"IPFS JSONアップロードに失敗しました: {e}")

    async def get_file(self, ipfs_hash: str) -> bytes:
        """
        IPFSからファイルを取得

        Args:
            ipfs_hash: IPFSハッシュ値

        Returns:
            bytes: ファイルのバイナリデータ
        """
        try:
            client = await self._get_http_client()

            response = await client.post(f"{self._api_url}/cat", params={"arg": ipfs_hash})
            response.raise_for_status()

            logger.info(f"File retrieved from IPFS: {ipfs_hash}")
            return response.content

        except Exception as e:
            logger.error(f"IPFS file retrieval failed: {e}")
            raise RuntimeError(f"IPFSファイル取得に失敗しました: {e}")

    async def get_json(self, ipfs_hash: str) -> Dict:
        """
        IPFSからJSONデータを取得

        Args:
            ipfs_hash: IPFSハッシュ値

        Returns:
            Dict: JSONデータ
        """
        try:
            file_data = await self.get_file(ipfs_hash)
            return json.loads(file_data.decode("utf-8"))

        except Exception as e:
            logger.error(f"IPFS JSON retrieval failed: {e}")
            raise RuntimeError(f"IPFS JSON取得に失敗しました: {e}")

    async def pin_file(self, ipfs_hash: str) -> bool:
        """
        ファイルをピン留め（永続保存）

        Args:
            ipfs_hash: IPFSハッシュ値

        Returns:
            bool: 成功フラグ
        """
        try:
            client = await self._get_http_client()

            response = await client.post(f"{self._api_url}/pin/add", params={"arg": ipfs_hash})
            response.raise_for_status()

            logger.info(f"File pinned: {ipfs_hash}")
            return True

        except Exception as e:
            logger.error(f"IPFS pin failed: {e}")
            return False

    async def unpin_file(self, ipfs_hash: str) -> bool:
        """
        ファイルのピン留めを解除

        Args:
            ipfs_hash: IPFSハッシュ値

        Returns:
            bool: 成功フラグ
        """
        try:
            client = await self._get_http_client()

            response = await client.post(f"{self._api_url}/pin/rm", params={"arg": ipfs_hash})
            response.raise_for_status()

            logger.info(f"File unpinned: {ipfs_hash}")
            return True

        except Exception as e:
            logger.error(f"IPFS unpin failed: {e}")
            return False

    async def get_file_info(self, ipfs_hash: str) -> Optional[Dict]:
        """
        ファイル情報を取得

        Args:
            ipfs_hash: IPFSハッシュ値

        Returns:
            Dict: ファイル情報
        """
        try:
            client = await self._get_http_client()

            response = await client.post(f"{self._api_url}/object/stat", params={"arg": ipfs_hash})
            response.raise_for_status()

            info = response.json()

            return {
                "hash": ipfs_hash,
                "size": info.get("CumulativeSize", 0),
                "links": info.get("NumLinks", 0),
                "retrieved_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"IPFS file info failed: {e}")
            return None

    async def is_connected(self) -> bool:
        """
        IPFS接続状態を確認

        Returns:
            bool: 接続状態
        """
        try:
            client = await self._get_http_client()

            response = await client.post(f"{self._api_url}/version")
            response.raise_for_status()

            version_info = response.json()
            logger.info(f"IPFS connected, version: {version_info.get('Version', 'unknown')}")
            return True

        except Exception as e:
            logger.warning(f"IPFS connection check failed: {e}")
            return False

    async def upload_csi_data_with_metadata(
        self, file_data: bytes, metadata: Dict, filename: str = None
    ) -> Dict[str, str]:
        """
        CSIデータとメタデータを統合してIPFSにアップロード

        Args:
            file_data: CSIデータファイルのバイナリ
            metadata: CSIデータのメタデータ
            filename: ファイル名

        Returns:
            Dict: IPFSハッシュ情報 {data_hash, metadata_hash, combined_hash}
        """
        try:
            # 1. CSIデータファイルをアップロード
            data_hash = await self.upload_file(file_data, filename)

            # 2. メタデータを強化
            enhanced_metadata = {
                **metadata,
                "ipfs_data_hash": data_hash,
                "file_size": len(file_data),
                "upload_timestamp": datetime.utcnow().isoformat(),
                "content_type": "application/octet-stream",
            }

            # 3. メタデータをIPFSにアップロード
            metadata_hash = await self.upload_json(enhanced_metadata)

            # 4. 統合オブジェクトを作成
            combined_object = {
                "type": "csi_data_package",
                "data_hash": data_hash,
                "metadata_hash": metadata_hash,
                "filename": filename,
                "created_at": datetime.utcnow().isoformat(),
            }

            # 5. 統合オブジェクトをアップロード
            combined_hash = await self.upload_json(combined_object)

            # 6. データとメタデータをピン留め
            await self.pin_file(data_hash)
            await self.pin_file(metadata_hash)
            await self.pin_file(combined_hash)

            logger.info(f"CSI data package uploaded to IPFS: {combined_hash}")

            return {"data_hash": data_hash, "metadata_hash": metadata_hash, "combined_hash": combined_hash}

        except Exception as e:
            logger.error(f"CSI data IPFS upload failed: {e}")
            raise RuntimeError(f"CSIデータのIPFS統合アップロードに失敗しました: {e}")

    async def retrieve_csi_data_package(self, combined_hash: str) -> Dict:
        """
        統合CSIデータパッケージをIPFSから取得

        Args:
            combined_hash: 統合オブジェクトのIPFSハッシュ

        Returns:
            Dict: 完全なCSIデータパッケージ
        """
        try:
            # 1. 統合オブジェクトを取得
            combined_object = await self.get_json(combined_hash)

            # 2. データファイルを取得
            data_hash = combined_object["data_hash"]
            file_data = await self.get_file(data_hash)

            # 3. メタデータを取得
            metadata_hash = combined_object["metadata_hash"]
            metadata = await self.get_json(metadata_hash)

            # 4. 完全なパッケージを構築
            package = {
                "combined_info": combined_object,
                "file_data": file_data,
                "metadata": metadata,
                "ipfs_hashes": {"data": data_hash, "metadata": metadata_hash, "combined": combined_hash},
            }

            logger.info(f"CSI data package retrieved from IPFS: {combined_hash}")
            return package

        except Exception as e:
            logger.error(f"CSI data package retrieval failed: {e}")
            raise RuntimeError(f"CSIデータパッケージの取得に失敗しました: {e}")

    async def delete_csi_data_package(self, combined_hash: str) -> bool:
        """
        CSIデータパッケージをIPFSから削除（ピン留め解除）

        Args:
            combined_hash: 統合オブジェクトのIPFSハッシュ

        Returns:
            bool: 削除成功フラグ
        """
        try:
            # 1. 統合オブジェクトを取得
            combined_object = await self.get_json(combined_hash)

            # 2. 各コンポーネントのピン留めを解除
            success_count = 0

            # データファイルのピン留め解除
            if await self.unpin_file(combined_object["data_hash"]):
                success_count += 1

            # メタデータのピン留め解除
            if await self.unpin_file(combined_object["metadata_hash"]):
                success_count += 1

            # 統合オブジェクトのピン留め解除
            if await self.unpin_file(combined_hash):
                success_count += 1

            success = success_count >= 2  # 少なくとも2つ成功すれば OK

            logger.info(f"CSI data package deletion: {success_count}/3 components unpinned")
            return success

        except Exception as e:
            logger.error(f"CSI data package deletion failed: {e}")
            return False

    async def close(self):
        """接続を閉じる"""
        if self._client:
            try:
                await self._client.aclose()
                self._client = None
                logger.info("IPFS HTTP client closed")
            except Exception as e:
                logger.error(f"Error closing IPFS HTTP client: {e}")


# シングルトンインスタンス
ipfs_service = IPFSService()
