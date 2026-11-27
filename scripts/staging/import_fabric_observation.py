#!/usr/bin/env python3
"""Index an already recorded, verified real observation in the reader's local catalog.

Does not generate a proof or submit a transaction. Requires reader API environment.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path
from uuid import UUID

from app.services.fabric_observation import FabricObservation
from app.services.observation_chain import observation_id, patient_ref
from app.services.observation_store import ObservationStore
from web3 import Web3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", type=UUID, required=True)
    parser.add_argument("--capture-id", type=UUID, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--source-csi", type=Path, required=True)
    args = parser.parse_args()
    patient, capture = str(args.patient_id), str(args.capture_id)
    chain = FabricObservation(profile="adaptive4004")
    if chain.manifest.get("topology", {}).get("singleHost") is not False:
        raise ValueError("An external consortium deployment is required")
    result = chain.request("/verify", {"observationId": Web3.to_hex(observation_id(capture))})
    if result.get("status") != "verified" or type(result.get("isNormal")) is not bool:
        raise ValueError("Only verified observations can be imported")
    if result.get("patientRef") != Web3.to_hex(patient_ref(patient)):
        raise ValueError("Patient reference mismatch")
    bundle = json.loads(args.bundle.read_text())
    proof = bundle["proof"]
    payload = {
        "observationId": Web3.to_hex(observation_id(capture)),
        "patientRef": Web3.to_hex(patient_ref(patient)),
        "observedAt": result["observedAt"],
        "durationSeconds": result["durationSeconds"],
        "proof": {"protocol": "groth16", "curve": "bn128", **{k: proof[k] for k in ["pi_a", "pi_b", "pi_c"]}},
        "publicSignals": bundle["publicSignals"],
    }
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    if result.get("payloadHash") != digest or result.get("deploymentId") != chain.manifest["deploymentId"]:
        raise ValueError("Proof bundle does not match the recorded payload/deployment")
    # This file hash is provenance supplied by the operator, not proof of sensor authenticity.
    source_hash = hashlib.sha256(args.source_csi.read_bytes()).hexdigest()
    db = ObservationStore()
    with db.connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO patients VALUES (?, ?, ?)", (patient, "患者 " + patient[:8], int(time.time()))
        )
    job = db.enqueue(
        capture,
        patient,
        result["observedAt"],
        result["durationSeconds"],
        source_hash,
        db.raw / (capture + ".csi"),
        ledger="fabric",
        proof_profile="adaptive4004",
    )
    if job["registry"] and job["registry"] != chain.manifest["deploymentId"]:
        raise ValueError("Existing catalog row is pinned to another deployment")
    db.update(
        capture,
        bundle=json.dumps(bundle),
        status="recorded",
        registry=chain.manifest["deploymentId"],
        tx_hash=result["transactionId"],
        error=None,
    )
    print(json.dumps({"captureId": capture, "patientId": patient, "verified": True, "newTransaction": False}))


if __name__ == "__main__":
    main()
