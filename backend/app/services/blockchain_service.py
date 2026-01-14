"""
ブロックチェーン連携サービス

ZKP証明をブロックチェーンに記録・取得するサービス
"""

import json
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging
from web3 import Web3
from web3.exceptions import ContractLogicError

logger = logging.getLogger(__name__)


class BlockchainService:
    """ブロックチェーン連携サービスクラス"""

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        contract_address: Optional[str] = None,
        account_private_key: Optional[str] = None
    ):
        """
        初期化

        Args:
            rpc_url: EthereumノードのRPC URL（デフォルト: 環境変数から取得）
            contract_address: ZKProofRegistryコントラクトのアドレス（デフォルト: 環境変数から取得）
            account_private_key: トランザクション署名用の秘密鍵（デフォルト: 環境変数から取得）
        """
        # 環境変数から設定を取得
        self.rpc_url = rpc_url or os.getenv('ETHEREUM_RPC_URL', 'http://localhost:8545')
        self.contract_address = contract_address or os.getenv('ZKPROOF_CONTRACT_ADDRESS')
        self.account_private_key = account_private_key or os.getenv('BLOCKCHAIN_PRIVATE_KEY')

        # Web3接続
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

        if not self.w3.is_connected():
            logger.warning(f"Failed to connect to Ethereum node at {self.rpc_url}")
            self.connected = False
            return

        self.connected = True
        logger.info(f"Connected to Ethereum node: Chain ID {self.w3.eth.chain_id}")

        # アカウント設定
        if self.account_private_key:
            self.account = self.w3.eth.account.from_key(self.account_private_key)
        else:
            # 秘密鍵がない場合は最初のアカウントを使用（開発環境のみ）
            accounts = self.w3.eth.accounts
            if accounts:
                self.account = accounts[0]
                logger.warning("Using first account from node (development mode)")
            else:
                logger.error("No account available for transactions")
                self.account = None

        # コントラクトをロード
        self.contract = None
        if self.contract_address:
            self._load_contract()
        else:
            logger.warning("Contract address not set. Blockchain recording disabled.")

    def _load_contract(self):
        """ZKProofRegistryコントラクトをロード"""
        try:
            # コントラクトABIを読み込み
            contract_build_path = Path(__file__).parent.parent.parent / "contracts" / "build" / "ZKProofRegistry.json"

            if not contract_build_path.exists():
                logger.error(f"Contract ABI not found: {contract_build_path}")
                return

            with open(contract_build_path, 'r') as f:
                contract_data = json.load(f)

            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.contract_address),
                abi=contract_data['abi']
            )

            logger.info(f"Loaded ZKProofRegistry contract at {self.contract_address}")

        except Exception as e:
            logger.error(f"Failed to load contract: {e}", exc_info=True)

    def is_available(self) -> bool:
        """ブロックチェーンサービスが利用可能か確認"""
        return self.connected and self.contract is not None and self.account is not None

    async def record_zkp_proof(
        self,
        device_id: str,
        proof: Dict[str, Any],
        public_signals: List[Any],
        proof_type: str = "full_similarity",
        data_hash: Optional[bytes] = None
    ) -> Optional[str]:
        """
        ZKP証明をブロックチェーンに記録

        Args:
            device_id: デバイスID
            proof: ZKP証明オブジェクト
            public_signals: 公開信号リスト
            proof_type: 証明タイプ（例: "cosine_similarity", "full_similarity"）
            data_hash: 元データのハッシュ（オプション）

        Returns:
            証明ID（bytes32をhex文字列に変換したもの）、失敗時はNone
        """
        if not self.is_available():
            logger.warning("Blockchain service not available")
            return None

        try:
            # 証明データをJSON文字列に変換
            proof_data_json = json.dumps(proof, separators=(',', ':'))
            public_signals_json = json.dumps(public_signals, separators=(',', ':'))

            # データハッシュがない場合は生成
            if data_hash is None:
                data_hash_str = hashlib.sha256(
                    (proof_data_json + public_signals_json).encode()
                ).digest()
            else:
                data_hash_str = data_hash if isinstance(data_hash, bytes) else bytes.fromhex(data_hash)

            logger.info(f"Recording ZKP proof for device {device_id}, type: {proof_type}")

            # トランザクションを構築
            if hasattr(self.account, 'address'):
                # アカウントオブジェクトの場合
                account_address = self.account.address
            else:
                # アドレス文字列の場合
                account_address = self.account

            tx = self.contract.functions.recordZKProof(
                device_id,
                proof_data_json,
                public_signals_json,
                proof_type,
                data_hash_str
            ).build_transaction({
                'from': account_address,
                'nonce': self.w3.eth.get_transaction_count(account_address),
                'gas': 2000000,
                'gasPrice': self.w3.eth.gas_price
            })

            # トランザクションに署名（秘密鍵がある場合）
            if self.account_private_key:
                signed_tx = self.w3.eth.account.sign_transaction(tx, self.account_private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            else:
                # 開発環境：署名なしでトランザクション送信
                tx_hash = self.w3.eth.send_transaction(tx)

            logger.info(f"Transaction sent: {tx_hash.hex()}")

            # トランザクションレシートを待機
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if tx_receipt['status'] == 1:
                # イベントログから証明IDを取得
                proof_recorded_event = self.contract.events.ZKProofRecorded()
                logs = proof_recorded_event.process_receipt(tx_receipt)

                if logs:
                    proof_id = logs[0]['args']['proofId']
                    proof_id_hex = proof_id.hex() if isinstance(proof_id, bytes) else f"0x{proof_id:064x}"
                    logger.info(f"ZKP proof recorded successfully. Proof ID: {proof_id_hex}")
                    return proof_id_hex
                else:
                    logger.error("No ZKProofRecorded event found in transaction receipt")
                    return None
            else:
                logger.error(f"Transaction failed: {tx_receipt}")
                return None

        except ContractLogicError as e:
            logger.error(f"Contract logic error: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Failed to record ZKP proof: {e}", exc_info=True)
            return None

    def get_zkp_proof_by_id(self, proof_id: str) -> Optional[Dict[str, Any]]:
        """
        証明IDからZKP証明を取得

        Args:
            proof_id: 証明ID（hex文字列）

        Returns:
            証明レコード、見つからない場合はNone
        """
        if not self.is_available():
            logger.warning("Blockchain service not available")
            return None

        try:
            # 証明IDをbytes32に変換
            if proof_id.startswith('0x'):
                proof_id_bytes = bytes.fromhex(proof_id[2:])
            else:
                proof_id_bytes = bytes.fromhex(proof_id)

            # コントラクトから取得
            record = self.contract.functions.getZKProofById(proof_id_bytes).call()

            # 構造体をディクショナリに変換
            result = {
                "device_id": record[0],
                "proof_data": json.loads(record[1]),
                "public_signals": json.loads(record[2]),
                "proof_type": record[3],
                "data_hash": record[4].hex() if isinstance(record[4], bytes) else f"0x{record[4]:064x}",
                "timestamp": record[5],
                "recorder": record[6],
                "verified": record[7],
                "exists": record[8]
            }

            return result

        except Exception as e:
            logger.error(f"Failed to get ZKP proof by ID: {e}", exc_info=True)
            return None

    def get_device_proof_ids(self, device_id: str) -> List[str]:
        """
        デバイスIDから証明IDリストを取得

        Args:
            device_id: デバイスID

        Returns:
            証明IDリスト（hex文字列）
        """
        if not self.is_available():
            logger.warning("Blockchain service not available")
            return []

        try:
            proof_ids = self.contract.functions.getDeviceProofIds(device_id).call()

            # bytes32をhex文字列に変換
            return [
                pid.hex() if isinstance(pid, bytes) else f"0x{pid:064x}"
                for pid in proof_ids
            ]

        except Exception as e:
            logger.error(f"Failed to get device proof IDs: {e}", exc_info=True)
            return []

    def get_latest_device_proof(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        デバイスの最新のZKP証明を取得

        Args:
            device_id: デバイスID

        Returns:
            最新の証明レコード、見つからない場合はNone
        """
        if not self.is_available():
            logger.warning("Blockchain service not available")
            return None

        try:
            proof_id_bytes = self.contract.functions.getLatestDeviceProofId(device_id).call()
            proof_id_hex = proof_id_bytes.hex() if isinstance(proof_id_bytes, bytes) else f"0x{proof_id_bytes:064x}"

            return self.get_zkp_proof_by_id(proof_id_hex)

        except Exception as e:
            logger.error(f"Failed to get latest device proof: {e}", exc_info=True)
            return None

    def verify_proof_on_chain(self, proof_id: str, is_valid: bool) -> bool:
        """
        ZKP証明を検証済みとしてマーク

        Args:
            proof_id: 証明ID（hex文字列）
            is_valid: 検証結果

        Returns:
            成功時True、失敗時False
        """
        if not self.is_available():
            logger.warning("Blockchain service not available")
            return False

        try:
            # 証明IDをbytes32に変換
            if proof_id.startswith('0x'):
                proof_id_bytes = bytes.fromhex(proof_id[2:])
            else:
                proof_id_bytes = bytes.fromhex(proof_id)

            # トランザクションを構築
            if hasattr(self.account, 'address'):
                account_address = self.account.address
            else:
                account_address = self.account

            tx = self.contract.functions.markProofAsVerified(
                proof_id_bytes,
                is_valid
            ).build_transaction({
                'from': account_address,
                'nonce': self.w3.eth.get_transaction_count(account_address),
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price
            })

            # トランザクションに署名
            if self.account_private_key:
                signed_tx = self.w3.eth.account.sign_transaction(tx, self.account_private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            else:
                tx_hash = self.w3.eth.send_transaction(tx)

            # トランザクションレシートを待機
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if tx_receipt['status'] == 1:
                logger.info(f"Proof {proof_id} marked as verified: {is_valid}")
                return True
            else:
                logger.error(f"Verification marking failed: {tx_receipt}")
                return False

        except Exception as e:
            logger.error(f"Failed to verify proof on chain: {e}", exc_info=True)
            return False

    def get_contract_info(self) -> Optional[Dict[str, Any]]:
        """
        コントラクト情報を取得

        Returns:
            コントラクト情報、失敗時はNone
        """
        if not self.is_available():
            return None

        try:
            info = self.contract.functions.getContractInfo().call()

            return {
                "owner": info[0],
                "total_proof_count": info[1],
                "current_block": info[2]
            }

        except Exception as e:
            logger.error(f"Failed to get contract info: {e}", exc_info=True)
            return None
