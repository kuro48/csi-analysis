"""Read-only verification of stored breathing proofs against a pinned contract."""
import json
from pathlib import Path

from web3 import Web3

from app.core.config import settings
from app.services.onchain_service import ChainUnavailable
from app.services.observation_protocol import validate_protocol


def observation_id(capture_id):
    return Web3.keccak(text="csi-observation:v1:" + capture_id)


def patient_ref(patient_id):
    return Web3.keccak(text="csi-patient:v1:" + patient_id)


class ObservationChain:
    def __init__(self, profile="legacy"):
        try:
            self.profile = profile
            self.manifest_path = (
                settings.ADAPTIVE_OBSERVATION_MANIFEST if profile == "adaptive4004" else settings.OBSERVATION_MANIFEST
            )
            self.manifest = json.loads(Path(self.manifest_path).read_text())
            m = self.manifest
            if m["kind"] != "breathing-observations" or m["chainId"] not in (11155111, 31337, 1337):
                raise ValueError("Unsupported observation deployment")
            validate_protocol(m, profile)
            rpc = (
                (settings.ADAPTIVE_ETHEREUM_RPC_URL or settings.ETHEREUM_RPC_URL)
                if profile == "adaptive4004"
                else settings.ETHEREUM_RPC_URL
            )
            self.w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))
            if self.w3.eth.chain_id != m["chainId"]:
                raise ValueError("Wrong chain")
            for prefix in ("registry", "verifier"):
                if Web3.to_hex(Web3.keccak(self.w3.eth.get_code(m[prefix + "Address"]))) != m[prefix + "CodeHash"]:
                    raise ValueError("Contract code mismatch")
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(m["registryAddress"]), abi=m["registryAbi"]
            )
            if (
                self.contract.functions.recorder().call().lower() != m["recorderAddress"].lower()
                or self.contract.functions.verifier().call().lower() != m["verifierAddress"].lower()
                or self.contract.functions.debugMode().call() != m["debugMode"]
            ):
                raise ValueError("Deployment configuration mismatch")
        except Exception as exc:
            raise ChainUnavailable("呼吸判定の検証先が未設定、またはチェーンに接続できません") from exc

    def metadata(self, capture_id, block="latest"):
        return self.contract.functions.getObservation(observation_id(capture_id)).call(block_identifier=block)

    def match_metadata(self, job, record):
        if (
            record[0] != patient_ref(job["patient_id"])
            or record[1] != job["observed_at"]
            or record[2] != job["duration"]
        ):
            raise ValueError("患者または計測時刻がチェーン上の記録と一致しません")

    def result(self, job):
        if (
            job["chain_id"] != self.manifest["chainId"]
            or (job["registry"] or "").lower() != self.contract.address.lower()
        ):
            raise ValueError("この計測の記録先と現在の設定が一致しません")
        record = self.metadata(job["id"])
        if not record[3]:
            return {"status": "pending"}
        self.match_metadata(job, record)
        head = self.w3.eth.block_number
        required_confirmations = (
            settings.ADAPTIVE_ONCHAIN_CONFIRMATIONS
            if job.get("proof_profile") == "adaptive4004"
            else settings.ONCHAIN_CONFIRMATIONS
        )
        confirmations = head - record[3] + 1
        if confirmations < required_confirmations:
            return {"status": "confirming", "confirmations": confirmations}
        # Pin metadata and verifier calls to the same confirmed snapshot.
        block_number = head - required_confirmations + 1
        block_hash = self.w3.eth.get_block(block_number)["hash"]
        stable = self.metadata(job["id"], block_number)
        if stable != record:
            raise ChainUnavailable("チェーンの更新中です。再照会してください")
        try:
            is_normal = self.contract.functions.verifyObservation(observation_id(job["id"])).call(
                block_identifier=block_number
            )
        except Exception as exc:
            from web3.exceptions import ContractLogicError

            if isinstance(exc, ContractLogicError) or "revert" in str(exc).lower():
                raise ValueError("記録された証明を検証できません。判定結果は表示しません") from exc
            raise
        if self.w3.eth.get_block(block_number)["hash"] != block_hash:
            raise ChainUnavailable("チェーンの更新中です。再照会してください")
        return {
            "status": "verified",
            "isNormal": bool(is_normal),
            "patientId": job["patient_id"],
            "observedAt": job["observed_at"],
            "durationSeconds": job["duration"],
            "verifiedAtBlock": block_number,
            "confirmations": confirmations,
            "transactionHash": job["tx_hash"],
            "chainId": self.manifest["chainId"],
            "debugInput": self.manifest["debugMode"],
        }
