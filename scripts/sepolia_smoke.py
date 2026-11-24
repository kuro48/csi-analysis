"""Seed one saved real-capture proof, then read a verified result from Sepolia."""
import fcntl
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.services.observation_chain import ObservationChain
from app.services.observation_store import ObservationStore

ROOT = Path(__file__).resolve().parents[1]


def main():
    work = Path(os.environ["SEPOLIA_MAC_WORK_DIR"])
    state_path = work / "smoke.json"
    chain = ObservationChain("adaptive4004")
    if chain.manifest["chainId"] != 11155111:
        raise ValueError("Sepolia only")
    db = ObservationStore()
    if sys.argv[1] == "seed":
        # Never race a live worker while installing a persisted proof fixture.
        with (db.root / "worker.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            readiness = json.loads((work / "proof-readiness.json").read_text())
            bundle_bytes = (ROOT / "docs/progress/2026-11-09-adaptive-4004/evm-proof-bundle.json").read_bytes()
            if (
                readiness.get("offlineProofValid") is not True
                or readiness["verificationKeyHash"] != chain.manifest["verificationKeyHash"]
                or readiness["bundleSha256"] != hashlib.sha256(bundle_bytes).hexdigest()
            ):
                raise ValueError("Run the pinned real-proof check first")
            if state_path.exists():
                state = json.loads(state_path.read_text())
                if state["registry"].lower() != chain.contract.address.lower():
                    raise ValueError("Existing smoke test is pinned to another deployment")
            else:
                state = {
                    "captureId": str(uuid4()),
                    "patientId": db.add_patient()["id"],
                    "registry": chain.contract.address,
                    "chainId": 11155111,
                    "sourceCaptureSha256": readiness["sourceCaptureSha256"],
                }
                state_path.write_text(json.dumps(state, indent=2) + "\n")
            job = db.enqueue(
                state["captureId"],
                state["patientId"],
                readiness["observedAt"],
                readiness["durationSeconds"],
                readiness["sourceCaptureSha256"],
                db.raw / (state["captureId"] + ".csi"),
                ledger="evm",
                proof_profile="adaptive4004",
            )
            if not job["bundle"]:
                db.save_bundle(job, json.loads(bundle_bytes))
            print(
                json.dumps(
                    {
                        **state,
                        "status": db.capture(state["captureId"])["status"],
                        "newProofGenerated": False,
                        "source": "saved real CSI proof",
                    }
                )
            )
    elif sys.argv[1] == "verify":
        state = json.loads(state_path.read_text())
        job = db.capture(state["captureId"])
        if job is None or job["chain_id"] is None:
            print(json.dumps({"status": job["status"] if job else "missing", "onchainVerified": False}))
            raise SystemExit(2)
        started = time.perf_counter()
        result = chain.result(job)
        report = {
            **state,
            "result": result,
            "verifyReadMs": (time.perf_counter() - started) * 1000,
            "verificationMethod": "Sepolia eth_call to verifyObservation; no verification transaction",
            "newProofGenerated": False,
        }
        if result["status"] == "verified":
            receipt = chain.w3.eth.get_transaction_receipt(job["tx_hash"])
            report["recordReceipt"] = {
                "transactionHash": job["tx_hash"],
                "blockNumber": receipt["blockNumber"],
                "status": receipt["status"],
                "gasUsed": receipt["gasUsed"],
                "effectiveGasPriceWei": receipt["effectiveGasPrice"],
                "feeWei": str(receipt["gasUsed"] * receipt["effectiveGasPrice"]),
                "confirmationsRequired": settings.ADAPTIVE_ONCHAIN_CONFIRMATIONS,
            }
            (work / "smoke-result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        if result["status"] != "verified":
            raise SystemExit(2)
    else:
        raise ValueError("Usage: sepolia_smoke.py seed|verify")


if __name__ == "__main__":
    main()
