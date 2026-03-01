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
        verifier_contract_address: Optional[str] = None,
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
        self.contract_address = (
            contract_address
            or os.getenv("ZKPROOF_CONTRACT_ADDRESS")
            or self._load_contract_address_from_artifact()
        )
        self.account_private_key = account_private_key or os.getenv('BLOCKCHAIN_PRIVATE_KEY')
        self.verifier_contract_address = (
            verifier_contract_address
            or os.getenv("ZKPROOF_VERIFIER_CONTRACT_ADDRESS")
            or self._load_verifier_address_from_artifact()
        )

        # Web3接続
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

        if not self.w3.is_connected():
            logger.warning(f"Failed to connect to Ethereum node at {self.rpc_url}")
            self.connected = False
            return

        self.connected = True
        logger.info(f"Connected to Ethereum node: Chain ID {self.w3.eth.chain_id}")

        # アカウント設定
        self.account = self._resolve_account()

        # コントラクトをロード
        self.contract = None
        if self.contract_address:
            self._load_contract()
        else:
            logger.warning("Contract address not set. Blockchain recording disabled.")

        # 検証コントラクトをロード
        self.verifier = None
        if self.verifier_contract_address:
            self._load_verifier_contract()
        else:
            logger.warning("Verifier contract address not set. On-chain verification disabled.")

    def _resolve_account(self):
        """トランザクション用のアカウントを解決"""
        if self.account_private_key:
            return self.w3.eth.account.from_key(self.account_private_key)

        # 秘密鍵がない場合は最初のアカウントを使用（開発環境のみ）
        accounts = self.w3.eth.accounts
        if accounts:
            logger.warning("Using first account from node (development mode)")
            return accounts[0]

        logger.error("No account available for transactions")
        return None

    def _load_contract_address_from_artifact(self) -> Optional[str]:
        """ビルド済みアーティファクトからコントラクトアドレスを取得"""
        contract_build_path = Path(__file__).parent.parent.parent / "contracts" / "build" / "ZKProofRegistry.json"
        if not contract_build_path.exists():
            return None

        try:
            with open(contract_build_path, "r") as f:
                contract_data = json.load(f)
            return contract_data.get("address")
        except Exception as e:
            logger.warning(f"Failed to load contract address from artifact: {e}")
            return None

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

    def _load_verifier_address_from_artifact(self) -> Optional[str]:
        """ビルド済みアーティファクトから検証コントラクトアドレスを取得"""
        contract_build_path = Path(__file__).parent.parent.parent / "contracts" / "build" / "FullSimilarityVerifier.json"
        if not contract_build_path.exists():
            return None

        try:
            with open(contract_build_path, "r") as f:
                contract_data = json.load(f)
            return contract_data.get("address")
        except Exception as e:
            logger.warning(f"Failed to load verifier address from artifact: {e}")
            return None

    def _load_verifier_contract(self):
        """ZKP検証コントラクトをロード"""
        try:
            contract_build_path = Path(__file__).parent.parent.parent / "contracts" / "build" / "FullSimilarityVerifier.json"
            if not contract_build_path.exists():
                logger.error(f"Verifier ABI not found: {contract_build_path}")
                return

            with open(contract_build_path, "r") as f:
                contract_data = json.load(f)

            self.verifier = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.verifier_contract_address),
                abi=contract_data["abi"]
            )
            logger.info(f"Loaded verifier contract at {self.verifier_contract_address}")
        except Exception as e:
            logger.error(f"Failed to load verifier contract: {e}", exc_info=True)

    def _get_account_address(self) -> Optional[str]:
        """送信元アドレスを取得"""
        if not self.account:
            return None

        return self.account.address if hasattr(self.account, "address") else self.account

    def _normalize_proof_id(self, proof_id: str) -> bytes:
        """証明IDをbytes32に変換"""
        if proof_id.startswith("0x"):
            return bytes.fromhex(proof_id[2:])
        return bytes.fromhex(proof_id)

    def _normalize_data_hash(
        self,
        proof_data_json: str,
        public_signals_json: str,
        data_hash: Optional[bytes]
    ) -> bytes:
        """データハッシュをbytesに正規化"""
        if data_hash is None:
            return hashlib.sha256((proof_data_json + public_signals_json).encode()).digest()

        return data_hash if isinstance(data_hash, bytes) else bytes.fromhex(data_hash)

    def _build_transaction(self, tx_func, gas: int) -> Optional[Dict[str, Any]]:
        """コントラクト関数からトランザクションを構築"""
        account_address = self._get_account_address()
        if not account_address:
            return None

        return tx_func.build_transaction({
            "from": account_address,
            "nonce": self.w3.eth.get_transaction_count(account_address),
            "gas": gas,
            "gasPrice": self.w3.eth.gas_price
        })

    def _estimate_gas_with_buffer(
        self,
        tx_func,
        default_gas: int,
        buffer_multiplier: float = 1.2,
        fallback_to_block_limit: bool = False
    ) -> int:
        """ガスを見積もってバッファを付与。失敗時はデフォルトを返す"""
        account_address = self._get_account_address()
        if not account_address:
            return default_gas

        try:
            estimated = tx_func.estimate_gas({"from": account_address})
            gas_limit = self.w3.eth.get_block("latest").gasLimit
            buffered = int(estimated * buffer_multiplier)
            if buffered >= gas_limit:
                logger.warning(
                    "Estimated gas exceeds block gas limit; using gas limit - 1. estimated=%s limit=%s",
                    estimated,
                    gas_limit
                )
                return max(gas_limit - 1, default_gas)

            return max(buffered, default_gas)
        except Exception as e:
            logger.warning(f"Gas estimation failed; using default gas. error={e}", exc_info=True)
            if fallback_to_block_limit:
                try:
                    gas_limit = self.w3.eth.get_block("latest").gasLimit
                    return max(gas_limit - 1, default_gas)
                except Exception:
                    return default_gas
            return default_gas

    def _prepare_onchain_payload(
        self,
        proof_data_json: str,
        public_signals_json: str,
        public_signals: List[Any]
    ) -> Dict[str, str]:
        """オンチェーンに載せるペイロードを整形（サイズ過大時はハッシュ化）"""
        store_full = os.getenv("ZKPROOF_STORE_FULL_DATA_ONCHAIN", "false").lower() == "true"
        max_chars = int(os.getenv("ZKPROOF_ONCHAIN_MAX_JSON_CHARS", "2048"))
        total_len = len(proof_data_json) + len(public_signals_json)

        if store_full and (max_chars <= 0 or total_len <= max_chars):
            return {"proof_data_json": proof_data_json, "public_signals_json": public_signals_json}

        if max_chars <= 0 or total_len <= max_chars:
            return {"proof_data_json": proof_data_json, "public_signals_json": public_signals_json}

        proof_hash = hashlib.sha256(proof_data_json.encode()).hexdigest()
        public_hash = hashlib.sha256(public_signals_json.encode()).hexdigest()
        logger.warning(
            "On-chain payload too large (%s chars). Storing hashes only. "
            "Set ZKPROOF_STORE_FULL_DATA_ONCHAIN=true or increase ZKPROOF_ONCHAIN_MAX_JSON_CHARS to override.",
            total_len
        )
        return {
            "proof_data_json": json.dumps({"sha256": proof_hash}),
            "public_signals_json": json.dumps({"sha256": public_hash, "count": len(public_signals)})
        }

    def _send_transaction(self, tx: Dict[str, Any]):
        """トランザクションを送信してハッシュを返す"""
        if self.account_private_key:
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.account_private_key)
            return self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        return self.w3.eth.send_transaction(tx)

    def _get_proof_id_from_receipt(self, tx_receipt) -> Optional[str]:
        """トランザクションレシートから証明IDを抽出"""
        proof_recorded_event = self.contract.events.ZKProofRecorded()
        logs = proof_recorded_event.process_receipt(tx_receipt)

        if not logs:
            logger.error("No ZKProofRecorded event found in transaction receipt")
            return None

        proof_id = logs[0]["args"]["proofId"]
        return proof_id.hex() if isinstance(proof_id, bytes) else f"0x{proof_id:064x}"

    def is_available(self) -> bool:
        """ブロックチェーンサービスが利用可能か確認"""
        return self.connected and self.contract is not None and self.account is not None

    def is_verifier_available(self) -> bool:
        """検証コントラクトが利用可能か確認"""
        return self.connected and self.verifier is not None

    def _parse_groth16_proof(self, proof: Dict[str, Any]):
        """Groth16証明をSolidity入力形式に変換"""
        try:
            a = [int(proof["pi_a"][0]), int(proof["pi_a"][1])]
            b = [
                [int(proof["pi_b"][0][1]), int(proof["pi_b"][0][0])],
                [int(proof["pi_b"][1][1]), int(proof["pi_b"][1][0])]
            ]
            c = [int(proof["pi_c"][0]), int(proof["pi_c"][1])]
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise ValueError(f"Invalid Groth16 proof format: {e}") from e

        return a, b, c

    def verify_zkp_proof_on_chain(self, proof: Dict[str, Any], public_signals: List[Any]) -> bool:
        """
        オンチェーン検証コントラクトでZKP証明を検証

        Args:
            proof: ZKP証明オブジェクト
            public_signals: 公開信号

        Returns:
            検証結果
        """
        if not self.is_verifier_available():
            logger.warning("Verifier contract not available")
            return False

        try:
            if not isinstance(public_signals, list):
                logger.warning("Public signals are not a list; skipping on-chain verification")
                return False
            if not all(k in proof for k in ("pi_a", "pi_b", "pi_c")):
                logger.warning("Proof data missing Groth16 keys; skipping on-chain verification")
                return False
            a, b, c = self._parse_groth16_proof(proof)
            public_signals_int = [int(x) for x in public_signals]
            return bool(self.verifier.functions.verifyProof(a, b, c, public_signals_int).call())
        except Exception as e:
            logger.error(f"On-chain verification failed: {e}", exc_info=True)
            return False

    def verify_and_mark_proof(
        self,
        proof_id: str,
        proof: Optional[Dict[str, Any]] = None,
        public_signals: Optional[List[Any]] = None,
    ) -> Optional[bool]:
        """
        証明IDからオンチェーン検証を行い、結果をブロックチェーンに記録

        Args:
            proof_id: 証明ID（hex文字列）
            proof: 生の証明データ（省略時はオンチェーンから取得）
            public_signals: 公開信号リスト（省略時はオンチェーンから取得）

        Returns:
            検証結果、失敗時はNone
        """
        # proof / public_signals が渡されなかった場合はオンチェーンから取得
        if proof is None or public_signals is None:
            proof_record = self.get_zkp_proof_by_id(proof_id)
            if not proof_record:
                logger.warning("Proof record not found on chain")
                return None
            if proof is None:
                proof = proof_record["proof_data"]
            if public_signals is None:
                public_signals = proof_record["public_signals"]

        # オンチェーンにハッシュのみ保存されている場合の検出
        # （public_signalsがリストでなくハッシュ辞書になっている）
        if not isinstance(public_signals, list):
            logger.warning(
                "public_signals is not a list (hash-only storage detected). "
                "On-chain Groth16 verification requires the actual signals. "
                "Marking as unverifiable (None returned)."
            )
            return None

        is_valid = self.verify_zkp_proof_on_chain(
            proof=proof,
            public_signals=public_signals,
        )
        if not self.verify_proof_on_chain(proof_id=proof_id, is_valid=is_valid):
            logger.warning("Failed to mark proof verification result on chain")
            return None

        return is_valid

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
            account_address = self._get_account_address()
            if not account_address:
                logger.error("No account available for recording proof")
                return None

            # 認可チェック（失敗時はトランザクションを送らない）
            try:
                if hasattr(self.contract.functions, "isAuthorizedRecorder"):
                    is_authorized = self.contract.functions.isAuthorizedRecorder(account_address).call()
                    if not is_authorized:
                        logger.error(f"Account not authorized to record proofs: {account_address}")
                        return None
            except Exception as e:
                logger.warning(f"Failed to check recorder authorization: {e}", exc_info=True)

            # 証明データをJSON文字列に変換
            proof_data_json = json.dumps(proof, separators=(',', ':'))
            public_signals_json = json.dumps(public_signals, separators=(',', ':'))

            # データハッシュを正規化
            data_hash_bytes = self._normalize_data_hash(proof_data_json, public_signals_json, data_hash)

            payload = self._prepare_onchain_payload(proof_data_json, public_signals_json, public_signals)

            logger.info(f"Recording ZKP proof for device {device_id}, type: {proof_type}")

            tx_func = self.contract.functions.recordZKProof(
                device_id,
                payload["proof_data_json"],
                payload["public_signals_json"],
                proof_type,
                data_hash_bytes
            )
            gas = self._estimate_gas_with_buffer(
                tx_func,
                default_gas=2000000,
                fallback_to_block_limit=True
            )

            # トランザクションを構築
            tx = self._build_transaction(tx_func, gas=gas)

            if not tx:
                logger.error("Failed to build transaction for recording proof")
                return None

            # トランザクションに署名（秘密鍵がある場合）
            tx_hash = self._send_transaction(tx)

            logger.info(f"Transaction sent: {tx_hash.hex()}")

            # トランザクションレシートを待機
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if tx_receipt['status'] == 1:
                # イベントログから証明IDを取得
                proof_id_hex = self._get_proof_id_from_receipt(tx_receipt)
                if not proof_id_hex:
                    return None

                logger.info(f"ZKP proof recorded successfully. Proof ID: {proof_id_hex}")
                return proof_id_hex

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
            proof_id_bytes = self._normalize_proof_id(proof_id)

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
            proof_id_bytes = self._normalize_proof_id(proof_id)

            # トランザクションを構築
            tx = self._build_transaction(self.contract.functions.markProofAsVerified(
                proof_id_bytes,
                is_valid
            ), gas=100000)

            if not tx:
                logger.error("Failed to build transaction for verification marking")
                return False

            # トランザクションに署名
            tx_hash = self._send_transaction(tx)

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
