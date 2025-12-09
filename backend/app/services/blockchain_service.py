"""
ブロックチェーンサービス - Web3.py統合
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from eth_account import Account
from eth_typing import Address
from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted

from app.core.config import settings

logger = logging.getLogger(__name__)


class BlockchainService:
    """
    ブロックチェーンサービス

    Web3.pyを使用してEthereumブロックチェーン（Ganache）と通信し、
    CSIデータのCIDを記録・取得する機能を提供します。
    """

    def __init__(self):
        """初期化"""
        self.enabled = settings.BLOCKCHAIN_ENABLED
        self.w3 = None
        self.contract = None
        self.account = None

        if self.enabled:
            try:
                self._initialize_web3()
                self._load_account()
                self._load_contract()
                logger.info("Blockchain service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize blockchain service: {e}")
                self.enabled = False

    def _initialize_web3(self):
        """Web3インスタンスを初期化"""
        try:
            self.w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))

            if not self.w3.is_connected():
                raise ConnectionError(f"Failed to connect to Ethereum node at {settings.ETHEREUM_RPC_URL}")

            # チェーンIDとネットワーク情報を取得
            chain_id = self.w3.eth.chain_id
            block_number = self.w3.eth.block_number

            logger.info(f"Connected to Ethereum network - Chain ID: {chain_id}, Block: {block_number}")

        except Exception as e:
            logger.error(f"Web3 initialization failed: {e}")
            raise

    def _load_account(self):
        """アカウント情報をロード"""
        try:
            if settings.BLOCKCHAIN_PRIVATE_KEY:
                # 秘密鍵からアカウントを作成
                self.account = Account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
                logger.info(f"Account loaded: {self.account.address}")
            else:
                # Ganacheのデフォルトアカウントを使用
                if self.w3.eth.accounts:
                    self.account_address = self.w3.eth.accounts[0]
                    logger.info(f"Using default account: {self.account_address}")
                else:
                    raise ValueError("No accounts available")

        except Exception as e:
            logger.error(f"Failed to load account: {e}")
            raise

    def _load_contract(self):
        """スマートコントラクトをロード"""
        try:
            # コントラクトアドレスが設定されていない場合はスキップ
            if settings.CONTRACT_ADDRESS == "0x0000000000000000000000000000000000000000":
                logger.warning("Contract address not set. Deploy contract first.")
                return

            # ABIファイルの読み込み
            abi_path = Path(settings.CONTRACT_ABI_PATH)

            if not abi_path.exists():
                logger.warning(f"Contract ABI file not found: {abi_path}")
                return

            with open(abi_path, "r") as f:
                contract_data = json.load(f)
                abi = contract_data.get("abi", contract_data)

            # コントラクトインスタンスを作成
            self.contract = self.w3.eth.contract(address=Web3.to_checksum_address(settings.CONTRACT_ADDRESS), abi=abi)

            logger.info(f"Contract loaded at: {settings.CONTRACT_ADDRESS}")

        except Exception as e:
            logger.error(f"Failed to load contract: {e}")
            raise

    async def record_csi_data_cid(self, device_id: str, ipfs_cid: str, metadata_hash: str) -> Dict[str, Any]:
        """
        CSIデータのCIDをブロックチェーンに記録

        Args:
            device_id: デバイスID
            ipfs_cid: IPFS CID (combined_hash)
            metadata_hash: メタデータのIPFS CID

        Returns:
            {
                "tx_hash": "0x...",
                "status": "pending",
                "block_number": None
            }
        """
        if not self.enabled or not self.contract:
            logger.warning("Blockchain service is disabled or contract not loaded")
            return {"tx_hash": None, "status": "disabled", "block_number": None}

        try:
            # トランザクションを構築
            function = self.contract.functions.recordCSIData(device_id, ipfs_cid, metadata_hash)

            # アカウントアドレス取得
            from_address = self.account.address if self.account else self.account_address

            # ガス見積もり
            try:
                gas_estimate = function.estimate_gas({"from": from_address})
                gas_limit = int(gas_estimate * 1.2)  # 20%のバッファ
            except Exception as e:
                logger.warning(f"Gas estimation failed, using default: {e}")
                gas_limit = settings.GAS_LIMIT

            # トランザクション構築
            tx_params = {
                "from": from_address,
                "gas": gas_limit,
                "gasPrice": settings.GAS_PRICE,
                "nonce": self.w3.eth.get_transaction_count(from_address),
            }

            # トランザクション送信
            if self.account:
                # 秘密鍵で署名して送信
                tx = function.build_transaction(tx_params)
                signed_tx = self.account.sign_transaction(tx)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            else:
                # Ganache unlocked accountで送信
                tx_hash = function.transact(tx_params)

            tx_hash_hex = self.w3.to_hex(tx_hash)

            logger.info(f"Transaction sent: {tx_hash_hex}")

            return {
                "tx_hash": tx_hash_hex,
                "status": "pending",
                "block_number": None,
                "device_id": device_id,
                "ipfs_cid": ipfs_cid,
            }

        except ContractLogicError as e:
            logger.error(f"Contract logic error: {e}")
            raise RuntimeError(f"ブロックチェーン記録エラー: {e}")
        except Exception as e:
            logger.error(f"Failed to record CID on blockchain: {e}")
            raise RuntimeError(f"ブロックチェーン記録に失敗しました: {e}")

    async def get_csi_data_by_cid(self, ipfs_cid: str) -> Optional[Dict[str, Any]]:
        """
        CIDからブロックチェーン上のデータ情報を取得

        Args:
            ipfs_cid: IPFS CID

        Returns:
            {
                "device_id": "device_001",
                "ipfs_cid": "Qm...",
                "metadata_hash": "Qm...",
                "timestamp": 1234567890,
                "recorder": "0x..."
            }
        """
        if not self.enabled or not self.contract:
            logger.warning("Blockchain service is disabled or contract not loaded")
            return None

        try:
            # コントラクトから情報取得
            result = self.contract.functions.getCSIDataByCID(ipfs_cid).call()

            # 結果をパース
            return {
                "device_id": result[0],
                "ipfs_cid": result[1],
                "metadata_hash": result[2],
                "timestamp": result[3],
                "recorder": result[4],
                "exists": result[5] if len(result) > 5 else True,
            }

        except ContractLogicError as e:
            logger.warning(f"CID not found on blockchain: {ipfs_cid}")
            return None
        except Exception as e:
            logger.error(f"Failed to get CID from blockchain: {e}")
            return None

    async def get_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        """
        トランザクション状態を確認

        Args:
            tx_hash: トランザクションハッシュ

        Returns:
            {
                "status": "confirmed" | "pending" | "failed",
                "block_number": 12345,
                "confirmations": 10,
                "gas_used": 123456
            }
        """
        if not self.enabled:
            return {"status": "disabled"}

        try:
            # トランザクションレシートを取得
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)

                current_block = self.w3.eth.block_number
                confirmations = current_block - receipt["blockNumber"]

                status = "confirmed" if receipt["status"] == 1 else "failed"

                return {
                    "status": status,
                    "block_number": receipt["blockNumber"],
                    "confirmations": confirmations,
                    "gas_used": receipt["gasUsed"],
                    "tx_hash": tx_hash,
                }

            except Exception:
                # レシートがない場合はpending
                try:
                    tx = self.w3.eth.get_transaction(tx_hash)
                    return {"status": "pending", "block_number": None, "confirmations": 0, "tx_hash": tx_hash}
                except Exception:
                    return {"status": "not_found", "tx_hash": tx_hash}

        except Exception as e:
            logger.error(f"Failed to get transaction status: {e}")
            return {"status": "error", "error": str(e), "tx_hash": tx_hash}

    async def verify_cid_exists(self, ipfs_cid: str) -> bool:
        """
        CIDがブロックチェーンに記録されているか確認

        Args:
            ipfs_cid: IPFS CID

        Returns:
            bool: 存在フラグ
        """
        if not self.enabled or not self.contract:
            return False

        try:
            result = self.contract.functions.cidExists(ipfs_cid).call()
            return result
        except Exception as e:
            logger.error(f"Failed to verify CID: {e}")
            return False

    async def get_device_cids(self, device_id: str) -> List[str]:
        """
        デバイスIDから関連するCIDリストを取得

        Args:
            device_id: デバイスID

        Returns:
            List[str]: CIDリスト
        """
        if not self.enabled or not self.contract:
            return []

        try:
            cids = self.contract.functions.getDeviceCIDs(device_id).call()
            return list(cids)
        except Exception as e:
            logger.error(f"Failed to get device CIDs: {e}")
            return []

    async def get_device_record_count(self, device_id: str) -> int:
        """
        デバイスの記録件数を取得

        Args:
            device_id: デバイスID

        Returns:
            int: 記録件数
        """
        if not self.enabled or not self.contract:
            return 0

        try:
            count = self.contract.functions.getDeviceRecordCount(device_id).call()
            return count
        except Exception as e:
            logger.error(f"Failed to get device record count: {e}")
            return 0

    async def wait_for_transaction_receipt(self, tx_hash: str, timeout: int = None) -> Optional[Dict[str, Any]]:
        """
        トランザクションレシートを待機

        Args:
            tx_hash: トランザクションハッシュ
            timeout: タイムアウト（秒）

        Returns:
            Optional[Dict]: トランザクションレシート
        """
        if not self.enabled:
            return None

        timeout = timeout or settings.TX_TIMEOUT

        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

            return {
                "tx_hash": self.w3.to_hex(receipt["transactionHash"]),
                "block_number": receipt["blockNumber"],
                "gas_used": receipt["gasUsed"],
                "status": "confirmed" if receipt["status"] == 1 else "failed",
            }

        except TimeExhausted:
            logger.warning(f"Transaction timeout: {tx_hash}")
            return {"tx_hash": tx_hash, "status": "timeout"}
        except Exception as e:
            logger.error(f"Failed to wait for transaction receipt: {e}")
            return None

    async def get_contract_info(self) -> Dict[str, Any]:
        """
        コントラクト情報を取得

        Returns:
            Dict: コントラクト情報
        """
        if not self.enabled or not self.contract:
            return {"enabled": False, "connected": False}

        try:
            info = self.contract.functions.getContractInfo().call()

            return {
                "enabled": True,
                "connected": self.w3.is_connected(),
                "contract_address": settings.CONTRACT_ADDRESS,
                "owner": info[0],
                "total_records": info[1],
                "current_block": info[2],
                "chain_id": self.w3.eth.chain_id,
            }

        except Exception as e:
            logger.error(f"Failed to get contract info: {e}")
            return {"enabled": True, "connected": self.w3.is_connected(), "error": str(e)}

    def is_connected(self) -> bool:
        """
        ブロックチェーン接続状態を確認

        Returns:
            bool: 接続状態
        """
        if not self.enabled or not self.w3:
            return False

        try:
            return self.w3.is_connected()
        except Exception:
            return False


# シングルトンインスタンス
blockchain_service = BlockchainService()
