"""Read-only RPC adapter for the immutable registry. Wallets sign transactions.

No private keys, server-paid transactions, or legacy verification flags are used.
"""
import json
import re
from pathlib import Path
from typing import Any

from eth_abi import encode
from web3 import Web3
from web3.exceptions import TransactionNotFound

from app.core.config import settings

SCALAR_FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617
BASE_FIELD = 21888242871839275222246405745257275088696311157297823662689037894645226208583


class ChainUnavailable(RuntimeError):
    pass


def decimal(value: Any, modulus: int) -> int:
    # JSON numbers cannot safely represent field elements in a browser.
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,77}", value):
        raise ValueError("Field elements must be canonical decimal strings")
    number = int(value)
    if number >= modulus:
        raise ValueError("Field element out of range")
    return number


def parse_proof(proof: dict, public_signals: list[str], count: int):
    if proof.get("protocol") != "groth16" or proof.get("curve") not in ("bn128", "bn254"):
        raise ValueError("Only Groth16 / BN254 proofs are supported")
    if len(public_signals) != count:
        raise ValueError("Public signal count does not match the deployed circuit")
    try:
        pa, pb, pc = proof["pi_a"], proof["pi_b"], proof["pi_c"]
        if (
            not all(isinstance(point, list) for point in (pa, pb, pc))
            or len(pa) != 3
            or len(pb) != 3
            or len(pc) != 3
            or any(not isinstance(row, list) or len(row) != 2 for row in pb)
        ):
            raise ValueError("Invalid proof dimensions")
        if pa[2] != "1" or pc[2] != "1" or pb[2] != ["1", "0"]:
            raise ValueError("Expected affine snarkjs proof")
        a = [decimal(v, BASE_FIELD) for v in pa[:2]]
        b = [[decimal(row[1], BASE_FIELD), decimal(row[0], BASE_FIELD)] for row in pb[:2]]
        c = [decimal(v, BASE_FIELD) for v in pc[:2]]
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("Invalid Groth16 proof shape") from exc
    return a, b, c, [decimal(v, SCALAR_FIELD) for v in public_signals]


class OnchainService:
    def __init__(self):
        if not settings.ONCHAIN_MANIFEST:
            raise ChainUnavailable("検証コントラクトが未設定です")
        try:
            self.manifest = json.loads(Path(settings.ONCHAIN_MANIFEST).read_text())
            if self.manifest.get("chainId") not in (11155111, 31337, 1337):
                raise ChainUnavailable("現在はEthereum SepoliaとローカルEVMのみ利用できます")
            self.w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL, request_kwargs={"timeout": 10}))
            if self.w3.eth.chain_id != self.manifest["chainId"]:
                raise ChainUnavailable("RPCのネットワークが設定と一致しません")
            address = Web3.to_checksum_address(self.manifest["registryAddress"])
            if Web3.to_hex(Web3.keccak(self.w3.eth.get_code(address))) != self.manifest["registryCodeHash"]:
                raise ChainUnavailable("デプロイ済みコントラクトのコードが一致しません")
            self.contract = self.w3.eth.contract(address=address, abi=self.manifest["registryAbi"])
            self.circuits = {c["name"]: c for c in self.manifest["circuits"]}
            for circuit in self.circuits.values():
                actual = self.contract.functions.circuits(bytes.fromhex(circuit["circuitId"][2:])).call()
                expected = (
                    circuit["address"],
                    bytes.fromhex(circuit["selector"][2:]),
                    circuit["publicSignalCount"],
                    bytes.fromhex(circuit["verificationKeyHash"][2:]),
                    bytes.fromhex(circuit["codeHash"][2:]),
                )
                if tuple(actual) != expected:
                    raise ChainUnavailable("検証回路の設定が一致しません")
        except ChainUnavailable:
            raise
        except Exception as exc:
            raise ChainUnavailable("ブロックチェーンに接続できません") from exc

    def status(self):
        return {
            "connected": True,
            "chainId": self.manifest["chainId"],
            "networkName": self.manifest["networkName"],
            "registryAddress": self.contract.address,
            "explorerUrl": self.manifest.get("explorerUrl", ""),
            "currentBlock": self.w3.eth.block_number,
            "totalVerified": self.contract.functions.totalVerified().call(),
            "confirmationsRequired": settings.ONCHAIN_CONFIRMATIONS,
            "circuits": list(self.circuits.values()),
        }

    def prepare(self, circuit_name: str, proof: dict, public_signals: list[str]):
        circuit = self.circuits.get(circuit_name)
        if circuit is None:
            raise ValueError("この回路の検証コントラクトはデプロイされていません")
        a, b, c, signals = parse_proof(proof, public_signals, circuit["publicSignalCount"])
        circuit_id = bytes.fromhex(circuit["circuitId"][2:])
        proof_id = Web3.to_hex(
            Web3.keccak(
                encode(
                    ["bytes32", "uint256[2]", "uint256[2][2]", "uint256[2]", "uint256[]"],
                    [circuit_id, a, b, c, signals],
                )
            )
        )
        existing = self.record(proof_id)
        if existing["exists"]:
            return {"alreadyVerified": True, "proofId": proof_id, "record": existing}
        function = self.contract.functions.verifyAndRecord(circuit_id, a, b, c, signals)
        # Simulation runs the exact contract path. It does NOT create a verified record.
        try:
            function.call({"from": "0x0000000000000000000000000000000000000001"})
        except Exception as exc:
            from web3.exceptions import ContractLogicError

            if isinstance(exc, ContractLogicError) or "revert" in str(exc).lower():
                raise ValueError("証明が検証コントラクトで拒否されました") from exc
            raise ChainUnavailable("送信前検証に失敗しました。接続を確認してください") from exc
        return {
            "alreadyVerified": False,
            "proofId": proof_id,
            "chainId": self.manifest["chainId"],
            "to": self.contract.address,
            "data": function._encode_transaction_data(),
            "value": "0x0",
        }

    def record(self, proof_id: str):
        record = self.contract.functions.records(bytes.fromhex(proof_id[2:])).call()
        exists = record[2] != "0x0000000000000000000000000000000000000000"
        confirmations = max(0, self.w3.eth.block_number - record[4] + 1) if exists else 0
        return {
            "proofId": proof_id,
            "exists": exists,
            "circuitId": Web3.to_hex(record[0]),
            "statementHash": Web3.to_hex(record[1]),
            "submitter": record[2],
            "timestamp": record[3],
            "blockNumber": record[4],
            "confirmations": confirmations,
            "status": ("confirmed" if confirmations >= settings.ONCHAIN_CONFIRMATIONS else "confirming")
            if exists
            else "not_found",
        }

    def receipt(self, tx_hash: str):
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return {"status": "pending", "transactionHash": tx_hash, "confirmations": 0}
        if not receipt["to"] or receipt["to"].lower() != self.contract.address.lower():
            raise ValueError("この検証コントラクトへのトランザクションではありません")
        if receipt["status"] != 1:
            return {"status": "reverted", "transactionHash": tx_hash, "confirmations": 0}
        block = self.w3.eth.get_block(receipt["blockNumber"])
        if block["hash"] != receipt["blockHash"]:
            return {"status": "pending", "transactionHash": tx_hash, "confirmations": 0}
        logs = self.contract.events.ProofVerified().process_receipt(receipt)
        logs = [log for log in logs if log["address"].lower() == self.contract.address.lower()]
        if len(logs) != 1:
            raise ValueError("検証成功イベントが見つかりません")
        record = self.record(Web3.to_hex(logs[0]["args"]["proofId"]))
        return {
            **record,
            "transactionHash": tx_hash,
            "gasUsed": receipt["gasUsed"],
            "blockHash": Web3.to_hex(receipt["blockHash"]),
        }
