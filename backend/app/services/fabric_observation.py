"""Permissioned ledger adapter. API holds only the reader bridge credential."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from web3 import Web3

from app.core.config import settings
from app.services.observation_chain import observation_id, patient_ref
from app.services.onchain_service import ChainUnavailable, parse_proof


class FabricObservation:
    def __init__(self, writer=False):
        try:
            self.manifest = json.loads(Path(settings.FABRIC_OBSERVATION_MANIFEST).read_text())
            self.writer = writer
            self.url = settings.FABRIC_WRITER_URL if writer else settings.FABRIC_READER_URL
            # Writer credential is read ONLY by the dedicated worker, never an API setting.
            self.token = os.environ.get("FABRIC_WRITER_TOKEN", "") if writer else settings.FABRIC_READER_TOKEN
            parsed = urlparse(self.url)
            if parsed.scheme != "https" and not (
                parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")
            ):
                raise ValueError("Remote bridges require HTTPS")
            if len(self.token) < 32:
                raise ValueError("Missing bridge token")
            actual = self.request("/configuration")
            if actual != self.manifest:
                raise ValueError("Fabric configuration mismatch")
        except Exception as exc:
            raise ChainUnavailable("Fabricの検証先が未設定、または接続できません") from exc

    def request(self, path, data=None):
        request = Request(
            self.url.rstrip("/") + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=150) as response:
                return json.load(response)
        except Exception as exc:
            raise ChainUnavailable("Fabricの処理を完了できません。判定結果は表示しません") from exc

    def match_metadata(self, job, result):
        if (
            result.get("deploymentId") != self.manifest["deploymentId"]
            or result.get("observationId") != Web3.to_hex(observation_id(job["id"]))
            or result.get("patientRef") != Web3.to_hex(patient_ref(job["patient_id"]))
            or result.get("observedAt") != job["observed_at"]
            or result.get("durationSeconds") != job["duration"]
        ):
            raise ValueError("患者・計測時刻・Fabric記録先が一致しません")

    def result(self, job):
        if job.get("ledger") != "fabric" or job["registry"] != self.manifest["deploymentId"]:
            raise ValueError("この計測のFabric記録先と現在の設定が一致しません")
        result = self.request("/verify", {"observationId": Web3.to_hex(observation_id(job["id"]))})
        self.match_metadata(job, result)
        if (
            result.get("status") != "verified"
            or type(result.get("isNormal")) is not bool
            or result.get("transactionId") != job["tx_hash"]
            or result.get("debugInput") is not self.manifest["debugMode"]
        ):
            raise ChainUnavailable("Fabricの検証応答が不正です。判定結果は表示しません")
        return {
            "status": "verified",
            "isNormal": result["isNormal"],
            "patientId": job["patient_id"],
            "observedAt": job["observed_at"],
            "durationSeconds": job["duration"],
            "transactionHash": result["transactionId"],
            "ledger": "fabric",
            "networkName": self.manifest["networkName"],
            "debugInput": self.manifest["debugMode"],
        }


def process_fabric_job(db, job):
    from app.services.breathing_certificate_service import BreathingCertificateService
    from app.services.observation_worker import generate_bundle

    chain = FabricObservation(writer=True)
    m = chain.manifest
    if job["registry"] is not None and job["registry"] != m["deploymentId"]:
        raise RuntimeError("Job deployment is pinned; restore its original manifest")
    db.update(job["id"], status="processing", registry=m["deploymentId"])
    job["registry"] = m["deploymentId"]
    if not job["bundle"]:
        service = BreathingCertificateService(auto_compile=False)
        exported = (
            Path(settings.FABRIC_OBSERVATION_MANIFEST).parent / "csi_breathing_certificate.vkey.json"
        ).read_bytes()
        vkey = service.keys_dir / "csi_breathing_certificate_verification_key.json"
        if "0x" + hashlib.sha256(exported).hexdigest() != m["verificationKeyHash"] or json.loads(
            vkey.read_text()
        ) != json.loads(exported):
            raise RuntimeError("Proving key does not match Fabric deployment")
        bundle = asyncio.run(generate_bundle(job, m["debugMode"]))
        db.save_bundle(job, bundle)
        job["bundle"] = json.dumps(bundle)
    else:
        Path(job["raw_path"]).unlink(missing_ok=True)
    bundle = json.loads(job["bundle"])
    _, _, _, signals = parse_proof(bundle["proof"], bundle["publicSignals"], 1)
    if signals[0] not in (0, 1):
        raise ValueError("Not a boolean breathing certificate")
    payload = {
        "observationId": Web3.to_hex(observation_id(job["id"])),
        "patientRef": Web3.to_hex(patient_ref(job["patient_id"])),
        "observedAt": job["observed_at"],
        "durationSeconds": job["duration"],
        **bundle,
    }
    # Same capture ID + exact persisted proof is idempotent, including uncertain commit recovery.
    reply = chain.request("/record", payload)
    chain.match_metadata(job, reply["result"])
    if reply["commit"]["code"] != 0 or reply["result"].get("status") != "recorded":
        raise ChainUnavailable("Fabric transaction did not commit successfully")
    tx = reply["result"]["transactionId"]
    if not isinstance(tx, str) or len(tx) != 64 or any(c not in "0123456789abcdef" for c in tx):
        raise ChainUnavailable("Invalid Fabric transaction ID")
    db.update(job["id"], tx_hash=tx, status="recorded", error=None)
