"""Single signing worker: python -m app.services.observation_worker [--once]."""
import argparse
import asyncio
import fcntl
import hashlib
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
from web3 import Web3
from web3.exceptions import TransactionNotFound

from app.core.config import settings
from app.services.breathing_certificate_service import BreathingCertificateService
from app.services.breathing_pipeline import (
    load_csi_matrix_with_timestamps,
    run_breathing_pipeline,
    run_breathing_pipeline_from_matrix,
)
from app.services.observation_chain import ObservationChain, observation_id
from app.services.observation_store import ObservationStore
from app.services.onchain_service import parse_proof

logger = logging.getLogger(__name__)


def validate_capture_timing(matrix, timestamps):
    # Existing estimator assumes uniform 100 Hz; never silently zero-pad normal captures.
    if len(matrix) < 5981 or len(timestamps) != len(matrix):
        raise ValueError("insufficient_capture_samples")
    intervals = np.diff(np.asarray(timestamps, dtype=np.int64)) / 1e9
    if np.any(intervals <= 0) or not np.all(np.isfinite(intervals)):
        raise ValueError("invalid_capture_timestamps")
    rate = 1 / np.mean(intervals)
    if not 95 <= rate <= 105 or np.std(intervals) / np.mean(intervals) > 0.2:
        raise ValueError("capture_requires_uniform_100hz")
    if (timestamps[5980] - timestamps[0]) / 1e9 < 57:
        raise ValueError("capture_window_too_short")


async def generate_bundle(job, debug_mode=False):
    service = BreathingCertificateService(auto_compile=False)
    if debug_mode:
        analysis = run_breathing_pipeline(job["raw_path"])
    else:
        if job["duration"] != 60:
            raise ValueError("capture_requires_60_second_window")
        matrix, timestamps = load_csi_matrix_with_timestamps(job["raw_path"])
        validate_capture_timing(matrix, timestamps)
        analysis = run_breathing_pipeline_from_matrix(matrix[:6000])
    cert = analysis["certificate_input"]
    result = await service.generate_proof(vmd_input=cert["vmdInput"], modes=cert["modes"], sel=cert["sel"])
    return {"proof": result["proof"], "publicSignals": result["publicSignals"]}


def load_account(chain):
    key_file = os.environ.get("OBSERVATION_RECORDER_KEY_FILE", "")
    if key_file:
        path = Path(key_file)
        if path.stat().st_mode & 0o077:
            raise RuntimeError("Recorder key file must have mode 0600")
        key = path.read_text().strip()
    else:
        key = os.environ.get("OBSERVATION_RECORDER_PRIVATE_KEY", "")
    if not key:
        raise RuntimeError("Configure OBSERVATION_RECORDER_KEY_FILE in the worker only")
    account = chain.w3.eth.account.from_key(key)
    if account.address.lower() != chain.manifest["recorderAddress"].lower():
        raise RuntimeError("Recorder key does not match the deployed contract")
    return account


def process_job(db, job):
    chain = ObservationChain()
    account = load_account(chain)
    m = chain.manifest
    if job["chain_id"] is not None and (
        job["chain_id"] != m["chainId"] or job["registry"].lower() != chain.contract.address.lower()
    ):
        raise RuntimeError("Job deployment is pinned; restore its original manifest")
    # Pin before proof generation or signing, including process restart recovery.
    db.update(job["id"], status="processing", chain_id=m["chainId"], registry=chain.contract.address)
    job.update(chain_id=m["chainId"], registry=chain.contract.address)
    if not job["bundle"]:
        service = BreathingCertificateService(auto_compile=False)
        vkey = service.keys_dir / "csi_breathing_certificate_verification_key.json"
        # JSON formatting can differ between exports; compare parsed keys with generated manifest key file.
        deployed_key = Path(settings.OBSERVATION_MANIFEST).parent / "csi_breathing_certificate.vkey.json"
        exported = deployed_key.read_bytes()
        if "0x" + hashlib.sha256(exported).hexdigest() != m["verificationKeyHash"] or json.loads(
            vkey.read_text()
        ) != json.loads(exported):
            raise RuntimeError("Proving key verification-key metadata does not match deployment")
        bundle = asyncio.run(generate_bundle(job, m["debugMode"]))
        db.save_bundle(job, bundle)
        job["bundle"] = json.dumps(bundle)
    else:
        Path(job["raw_path"]).unlink(missing_ok=True)
    bundle = json.loads(job["bundle"])
    a, b, c, signals = parse_proof(bundle["proof"], bundle["publicSignals"], 1)
    if signals[0] not in (0, 1):
        raise ValueError("Not a boolean breathing certificate")
    existing = chain.metadata(job["id"])
    if existing[3]:
        chain.match_metadata(job, existing)
        result = chain.result(job)
        if result["status"] == "verified":
            db.update(job["id"], status="recorded", error=None, signed_tx=None)
            return
        db.update(job["id"], status="submitted", next_attempt=int(time.time()) + 10)
        return
    if not job["signed_tx"]:
        from app.services.observation_chain import patient_ref

        function = chain.contract.functions.recordObservation(
            observation_id(job["id"]),
            patient_ref(job["patient_id"]),
            job["observed_at"],
            job["duration"],
            a,
            b,
            c,
            signals,
        )
        tx = function.build_transaction(
            {
                "from": account.address,
                "chainId": m["chainId"],
                "nonce": chain.w3.eth.get_transaction_count(account.address, "pending"),
            }
        )
        # Limit fees per transaction; no automatic funding or unbounded gas spend.
        max_fee = tx.get("maxFeePerGas", tx.get("gasPrice", 0))
        if tx["gas"] * max_fee > int(os.environ.get("OBSERVATION_MAX_TX_WEI", "10000000000000000")):
            raise RuntimeError("Transaction exceeds configured fee cap")
        signed = account.sign_transaction(tx)
        raw = signed.rawTransaction
        job["signed_tx"] = Web3.to_hex(raw)
        job["tx_hash"] = Web3.to_hex(Web3.keccak(raw))
        # Commit signed bytes before broadcast so retries reuse the SAME transaction.
        db.update(job["id"], signed_tx=job["signed_tx"], tx_hash=job["tx_hash"], status="submitted")
    try:
        receipt = chain.w3.eth.get_transaction_receipt(job["tx_hash"])
    except TransactionNotFound:
        try:
            chain.w3.eth.send_raw_transaction(bytes.fromhex(job["signed_tx"][2:]))
        except ValueError as exc:
            if "already known" not in str(exc).lower():
                raise
        db.update(job["id"], status="submitted", next_attempt=int(time.time()) + 10)
        return
    if receipt["status"] != 1:
        # The nonce is consumed. Stop this job; a deliberate operator retry may
        # sign a fresh transaction, while other queued captures can continue.
        db.update(job["id"], status="failed", error="transaction_reverted", signed_tx=None)
        return
    # A successful receipt without matching storage must never become a result.
    raise RuntimeError("Transaction receipt has no matching observation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO)
    db = ObservationStore()
    with (db.root / "worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            db.expire_raw()
            job = db.next_job()
            if job:
                try:
                    process_job(db, job)
                except Exception as exc:
                    attempts = job["attempts"] + 1
                    quality_errors = {
                        "insufficient_capture_samples",
                        "invalid_capture_timestamps",
                        "capture_requires_uniform_100hz",
                        "capture_window_too_short",
                        "capture_requires_60_second_window",
                    }
                    quality_error = str(exc) if str(exc) in quality_errors else None
                    # Log category only: RPC error payloads can contain proof/capture information.
                    logger.error("Capture %s failed (%s), attempt %s", job["id"], type(exc).__name__, attempts)
                    db.update(
                        job["id"],
                        attempts=attempts,
                        error=quality_error or "processing_failed",
                        status="failed" if quality_error or attempts >= 5 else "queued",
                        next_attempt=int(time.time()) + min(300, 10 * 2**attempts),
                    )
            if args.once:
                return
            time.sleep(2)


if __name__ == "__main__":
    main()
