"""
IPFS サービス
"""

import asyncio
import json
import logging
from typing import Dict, Optional, Tuple, Union
from datetime import datetime
import ipfshttpclient

from app.core.config import settings

logger = logging.getLogger(__name__)


class IPFSService:
    """IPFS クライアントサービス"""

    def __init__(self):
        self.client = None
        # IPFSクライアント接続設定（Docker環境対応）
        if settings.IPFS_HOST in ["localhost", "ipfs"]:
            # Docker環境では dns4 形式を使用
            self._connection_url = f"/dns4/ipfs/tcp/{settings.IPFS_PORT}"
        else:
            self._connection_url = f"{settings.IPFS_HOST}:{settings.IPFS_PORT}"

    async def _get_client(self) -> ipfshttpclient.Client:
        """IPFS クライアントを取得（接続確認付き）"""
        if self.client is None:
            try:
                # 同期クライアントを作成（ipfshttpclientは非同期対応していない）
                self.client = ipfshttpclient.connect(self._connection_url, timeout=10)
                # 接続テスト
                self.client.version()
                logger.info(f"IPFS connection established: {self._connection_url}")
            except Exception as e:
                logger.error(f"Failed to connect to IPFS: {e}")
                raise ConnectionError(f"IPFS接続に失敗しました: {e}")

        return self.client

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
            client = await self._get_client()

            # バックグラウンドスレッドで同期処理を実行
            def _upload():
                # BytesIOを使用してファイルオブジェクトとして扱う
                import io
                file_obj = io.BytesIO(file_data)

                if filename:
                    # ファイル名付きでアップロード
                    result = client.add(file_obj, pin=True, wrap_with_directory=False)
                else:
                    # バイナリデータのみでアップロード
                    result = client.add(file_obj, pin=True)

                # レスポンスがリストの場合は最後の要素、辞書の場合はそのまま使用
                if isinstance(result, list):
                    return result[-1]['Hash']
                else:
                    return result['Hash']

            # 非同期で実行
            ipfs_hash = await asyncio.get_event_loop().run_in_executor(None, _upload)

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
            json_data = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            return await self.upload_file(json_data, filename)

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
            client = await self._get_client()

            def _get():
                return client.cat(ipfs_hash)

            # 非同期で実行
            file_data = await asyncio.get_event_loop().run_in_executor(None, _get)

            logger.info(f"File retrieved from IPFS: {ipfs_hash}")
            return file_data

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
            return json.loads(file_data.decode('utf-8'))

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
            client = await self._get_client()

            def _pin():
                result = client.pin.add(ipfs_hash)
                return result is not None

            success = await asyncio.get_event_loop().run_in_executor(None, _pin)

            if success:
                logger.info(f"File pinned: {ipfs_hash}")

            return success

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
            client = await self._get_client()

            def _unpin():
                result = client.pin.rm(ipfs_hash)
                return result is not None

            success = await asyncio.get_event_loop().run_in_executor(None, _unpin)

            if success:
                logger.info(f"File unpinned: {ipfs_hash}")

            return success

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
            client = await self._get_client()

            def _get_info():
                return client.object.stat(ipfs_hash)

            info = await asyncio.get_event_loop().run_in_executor(None, _get_info)

            return {
                'hash': ipfs_hash,
                'size': info.get('CumulativeSize', 0),
                'links': info.get('NumLinks', 0),
                'retrieved_at': datetime.utcnow().isoformat()
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
            client = await self._get_client()

            def _check():
                version = client.version()
                return version is not None

            return await asyncio.get_event_loop().run_in_executor(None, _check)

        except Exception:
            return False

    async def upload_csi_data_with_metadata(
        self,
        file_data: bytes,
        metadata: Dict,
        filename: str = None
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
                "content_type": "application/octet-stream"
            }

            # 3. メタデータをIPFSにアップロード
            metadata_hash = await self.upload_json(enhanced_metadata)

            # 4. 統合オブジェクトを作成
            combined_object = {
                "type": "csi_data_package",
                "data_hash": data_hash,
                "metadata_hash": metadata_hash,
                "filename": filename,
                "created_at": datetime.utcnow().isoformat()
            }

            # 5. 統合オブジェクトをアップロード
            combined_hash = await self.upload_json(combined_object)

            # 6. データとメタデータをピン留め
            await self.pin_file(data_hash)
            await self.pin_file(metadata_hash)
            await self.pin_file(combined_hash)

            logger.info(f"CSI data package uploaded to IPFS: {combined_hash}")

            return {
                "data_hash": data_hash,
                "metadata_hash": metadata_hash,
                "combined_hash": combined_hash
            }

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
                "ipfs_hashes": {
                    "data": data_hash,
                    "metadata": metadata_hash,
                    "combined": combined_hash
                }
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

    def close(self):
        """接続を閉じる"""
        if self.client:
            try:
                self.client.close()
                self.client = None
                logger.info("IPFS connection closed")
            except Exception as e:
                logger.error(f"Error closing IPFS connection: {e}")


# シングルトンインスタンス
ipfs_service = IPFSService()