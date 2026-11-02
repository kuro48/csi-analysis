import io
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints import observations
from app.core.config import settings
from app.services.observation_chain import ObservationChain, patient_ref
from app.services.observation_store import ObservationStore


@pytest.fixture
def context(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "OBSERVATION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "OPERATOR_API_TOKEN", "t" * 40)
    app = FastAPI()
    app.include_router(observations.router, prefix="/observations")
    with TestClient(app) as client:
        yield client, ObservationStore(), {"Authorization": "Bearer " + "t" * 40}


def ingest(client, headers, patient, capture_id=None, **updates):
    fields = {
        "patient_id": patient,
        "capture_id": capture_id or str(uuid4()),
        "observed_at": "2026-01-01T00:00:00+00:00",
        "duration_seconds": "60",
    }
    fields.update(updates)
    return client.post(
        "/observations/captures",
        headers=headers,
        data=fields,
        files={"file": ("test.csi", io.BytesIO(b"private-csi"), "application/octet-stream")},
    )


def test_catalog_write_auth_and_no_secret_or_result_leak(context, monkeypatch):
    client, db, headers = context
    assert client.post("/observations/patients").status_code == 401
    monkeypatch.setattr(settings, "OPERATOR_API_TOKEN", "")
    assert client.post("/observations/patients").status_code == 401
    monkeypatch.setattr(settings, "OPERATOR_API_TOKEN", "t" * 40)
    patient = client.post("/observations/patients", headers=headers).json()["id"]
    assert client.get("/observations/patients").json()["patients"][0]["id"] == patient
    assert ingest(client, {}, patient).status_code == 401
    response = ingest(client, headers, patient)
    assert response.status_code == 202
    job = response.json()["id"]
    public = client.get(f"/observations/patients/{patient}/measurements")
    assert public.headers["cache-control"] == "no-store"
    assert "raw" not in public.text and "isNormal" not in public.text and "bundle" not in public.text
    assert client.get(f"/observations/captures/{job}").status_code == 401
    result = client.post(f"/observations/measurements/{job}/verify")
    assert result.status_code == 202 and "isNormal" not in result.json()
    db.update(job, status="failed")
    assert "isNormal" not in client.post(f"/observations/measurements/{job}/verify").json()


def test_capture_idempotency_conflict_and_file_cleanup(context):
    client, db, headers = context
    patient = db.add_patient()["id"]
    capture_id = str(uuid4())
    first = ingest(client, headers, patient, capture_id)
    again = ingest(client, headers, patient, capture_id)
    assert first.json() == again.json()
    assert len(list(db.raw.iterdir())) == 1
    assert ingest(client, headers, patient, capture_id, duration_seconds="61").status_code == 409
    assert len(list(db.raw.iterdir())) == 1
    assert ingest(client, headers, patient, observed_at="2026-01-01T00:00:00").status_code == 422
    assert ingest(client, headers, str(uuid4())).status_code == 404
    assert ingest(client, headers, patient, observed_at="2100-01-01T00:00:00Z").status_code == 422
    assert client.get(f"/observations/patients/{patient}/measurements?start_at=1&end_at=2").json()["measurements"] == []
    assert len(client.get(f"/observations/patients/{patient}/measurements").json()["measurements"]) == 1
    assert client.get(f"/observations/patients/{patient}/measurements?start_at=2&end_at=1").status_code == 422


def test_queue_limit_keeps_existing_capture_idempotent(context, monkeypatch):
    client, db, headers = context
    monkeypatch.setattr(settings, "OBSERVATION_MAX_PENDING", 1)
    patient = db.add_patient()["id"]
    first = str(uuid4())
    assert ingest(client, headers, patient, first).status_code == 202
    assert ingest(client, headers, patient, first).status_code == 202
    assert ingest(client, headers, patient).status_code == 429
    assert len(list(db.raw.iterdir())) == 1


def test_uncertain_signed_transaction_blocks_later_nonces(context):
    client, db, headers = context
    patient = db.add_patient()["id"]
    first = ingest(client, headers, patient).json()["id"]
    ingest(client, headers, patient)
    db.update(first, signed_tx="0x1234", next_attempt=int(time.time()) + 100)
    assert db.next_job() is None
    db.update(first, next_attempt=0)
    assert db.next_job()["id"] == first
    db.update(first, status="failed")
    assert db.next_job() is None
    assert client.post(f"/observations/captures/{first}/retry", headers=headers).status_code == 200
    assert db.next_job()["signed_tx"] == "0x1234"


def test_worker_persists_before_broadcast_and_reuses_signed_bytes(context, monkeypatch):
    from app.services import observation_worker as worker
    from web3.exceptions import TransactionNotFound
    from tests.unit.test_onchain import PROOF

    client, db, headers = context
    job_id = ingest(client, headers, db.add_patient()["id"]).json()["id"]
    db.save_bundle(db.capture(job_id), {"proof": PROOF, "publicSignals": ["0"]})
    sent, signed = [], []
    address = "0x" + "a" * 40

    def sign(tx):
        signed.append(tx)
        return SimpleNamespace(rawTransaction=b"signed-transaction")

    def broadcast(raw):
        assert db.capture(job_id)["signed_tx"] is not None
        assert db.capture(job_id)["tx_hash"] is not None
        sent.append(raw)
        if len(sent) == 1:
            raise ConnectionError("Response lost AFTER broadcast")

    def missing(_):
        raise TransactionNotFound()

    chain = SimpleNamespace(
        manifest={"chainId": 31337},
        metadata=lambda _: [b"", 0, 0, 0, b""],
        w3=SimpleNamespace(
            eth=SimpleNamespace(
                get_transaction_count=lambda *a: 0, get_transaction_receipt=missing, send_raw_transaction=broadcast
            )
        ),
        contract=SimpleNamespace(
            address=address,
            functions=SimpleNamespace(
                recordObservation=lambda *a: SimpleNamespace(
                    build_transaction=lambda args: {**args, "gas": 400000, "gasPrice": 1}
                )
            ),
        ),
    )
    monkeypatch.setattr(worker, "ObservationChain", lambda: chain)
    monkeypatch.setattr(worker, "load_account", lambda _: SimpleNamespace(address=address, sign_transaction=sign))
    with pytest.raises(ConnectionError):
        worker.process_job(db, db.capture(job_id))
    worker.process_job(db, db.capture(job_id))
    assert len(signed) == 1 and sent == [b"signed-transaction", b"signed-transaction"]


def test_persistent_queue_deletes_raw_after_proof_and_expires_failed_capture(context):
    client, db, headers = context
    patient = db.add_patient()["id"]
    job_id = ingest(client, headers, patient).json()["id"]
    fresh = ObservationStore()
    job = fresh.next_job()
    assert job["id"] == job_id
    fresh.save_bundle(job, {"proof": "test", "publicSignals": ["0"]})
    assert len(list(db.raw.iterdir())) == 0
    assert json.loads(db.capture(job_id)["bundle"])["publicSignals"] == ["0"]
    old = ingest(client, headers, patient).json()["id"]
    with db.connect() as conn:
        conn.execute("UPDATE captures SET created_at=0 WHERE id=?", (old,))
    fresh.expire_raw()
    assert db.capture(old)["error"] == "raw_expired"
    assert not list(db.raw.iterdir())
    assert client.post(f"/observations/captures/{old}/retry", headers=headers).status_code == 410


def test_api_releases_only_verified_value_and_failures_have_no_output(context, monkeypatch):
    client, db, headers = context
    job_id = ingest(client, headers, db.add_patient()["id"]).json()["id"]
    db.update(job_id, tx_hash="0x" + "1" * 64)
    monkeypatch.setattr(
        observations,
        "ObservationChain",
        lambda: SimpleNamespace(result=lambda _: {"status": "verified", "isNormal": False}),
    )
    result = client.post(f"/observations/measurements/{job_id}/verify")
    assert result.status_code == 200 and result.json()["isNormal"] is False

    def invalid(_):
        raise ValueError("invalid proof")

    monkeypatch.setattr(observations, "ObservationChain", lambda: SimpleNamespace(result=invalid))
    result = client.post(f"/observations/measurements/{job_id}/verify")
    assert result.status_code == 422 and "isNormal" not in result.json()


def test_chain_result_checks_binding_confirmations_and_calls_verifier(monkeypatch):
    monkeypatch.setattr(settings, "ONCHAIN_CONFIRMATIONS", 2)
    job = {
        "id": str(uuid4()),
        "patient_id": str(uuid4()),
        "observed_at": 100,
        "duration": 60,
        "chain_id": 31337,
        "registry": "0x" + "a" * 40,
        "tx_hash": "0x" + "b" * 64,
    }
    record = [patient_ref(job["patient_id"]), 100, 60, 10, b"d" * 32]
    calls = []

    def checked(**kwargs):
        calls.append(kwargs)
        return False

    chain = ObservationChain.__new__(ObservationChain)
    chain.manifest = {"chainId": 31337, "debugMode": False}
    chain.metadata = lambda *args: record
    chain.w3 = SimpleNamespace(eth=SimpleNamespace(block_number=10, get_block=lambda _: {"hash": b"b" * 32}))
    chain.contract = SimpleNamespace(
        address=job["registry"], functions=SimpleNamespace(verifyObservation=lambda _: SimpleNamespace(call=checked))
    )
    assert chain.result(job)["status"] == "confirming" and not calls
    chain.w3.eth.block_number = 11
    result = chain.result(job)
    assert result["isNormal"] is False and calls == [{"block_identifier": 10}]
    record[1] = 101
    with pytest.raises(ValueError, match="時刻"):
        chain.result(job)
    record[1] = 100
    job["patient_id"] = str(uuid4())
    with pytest.raises(ValueError, match="患者"):
        chain.result(job)


def test_normal_capture_rejects_short_irregular_or_wrong_rate_input():
    import numpy as np
    from app.services.observation_worker import validate_capture_timing

    matrix = np.zeros((6000, 3))
    timestamps = np.arange(6000, dtype=np.int64) * 10_000_000
    validate_capture_timing(matrix, timestamps)
    with pytest.raises(ValueError, match="insufficient"):
        validate_capture_timing(matrix[:150], timestamps[:150])
    with pytest.raises(ValueError, match="100hz"):
        validate_capture_timing(matrix, timestamps * 2)
    timestamps[10] = timestamps[9]
    with pytest.raises(ValueError, match="timestamps"):
        validate_capture_timing(matrix, timestamps)
