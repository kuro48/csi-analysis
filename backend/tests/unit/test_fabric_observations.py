import json
from unittest.mock import Mock

import pytest
from web3 import Web3

from app.api.endpoints import observations
from app.core.config import settings
from app.services.fabric_observation import FabricObservation, process_fabric_job
from app.services.observation_chain import observation_id, patient_ref
from app.services.onchain_service import ChainUnavailable
from tests.unit.test_observations import context, ingest  # noqa: F401


def test_capture_pins_ledger_and_rejects_switch_on_retry(context):
    client, db, headers = context
    patient = db.add_patient()["id"]
    response = ingest(client, headers, patient, ledger="fabric")
    assert response.status_code == 202
    job = db.capture(response.json()["id"])
    assert job["ledger"] == "fabric"
    assert ingest(client, headers, patient, job["id"], ledger="evm").status_code == 409
    assert ingest(client, headers, patient, ledger="unknown").status_code == 422
    assert db.observations(patient)[0]["ledger"] == "fabric"
    assert "isNormal" not in client.post(f'/observations/measurements/{job["id"]}/verify').json()


@pytest.fixture
def fabric(context):
    client, db, headers = context
    patient = db.add_patient()["id"]
    capture = ingest(client, headers, patient, ledger="fabric").json()["id"]
    db.update(capture, registry="deployment", tx_hash="a" * 64, status="recorded")
    job = db.capture(capture)
    chain = FabricObservation.__new__(FabricObservation)
    chain.manifest = {"deploymentId": "deployment", "networkName": "Fabric test", "debugMode": True}
    response = {
        "status": "verified",
        "isNormal": False,
        "deploymentId": "deployment",
        "debugInput": True,
        "observationId": Web3.to_hex(observation_id(capture)),
        "patientRef": Web3.to_hex(patient_ref(patient)),
        "observedAt": job["observed_at"],
        "durationSeconds": job["duration"],
        "transactionId": "a" * 64,
    }
    chain.request = Mock(return_value=response)
    return client, db, job, chain, response


def test_verified_false_remains_valid_and_routes_to_fabric(fabric, monkeypatch):
    client, db, job, chain, response = fabric
    monkeypatch.setattr(observations, "FabricObservation", lambda: chain)
    result = client.post(f'/observations/measurements/{job["id"]}/verify')
    assert result.status_code == 200
    assert result.json()["status"] == "verified" and result.json()["isNormal"] is False
    assert result.json()["ledger"] == "fabric"
    assert "chainId" not in result.json() and "confirmations" not in result.json()


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "recorded"),
        ("isNormal", "false"),
        ("patientRef", "other"),
        ("observedAt", 1),
        ("durationSeconds", 1),
        ("transactionId", "other"),
        ("deploymentId", "other"),
        ("observationId", "other"),
        ("debugInput", False),
    ],
)
def test_reject_misbound_or_unverified_result(fabric, monkeypatch, field, value):
    client, db, job, chain, response = fabric
    response[field] = value
    monkeypatch.setattr(observations, "FabricObservation", lambda: chain)
    result = client.post(f'/observations/measurements/{job["id"]}/verify')
    assert result.status_code in (422, 503)
    assert "isNormal" not in result.json()


def test_reader_network_failure_has_no_output(fabric, monkeypatch):
    client, db, job, chain, _ = fabric
    chain.request.side_effect = ChainUnavailable("unavailable")
    monkeypatch.setattr(observations, "FabricObservation", lambda: chain)
    response = client.post(f'/observations/measurements/{job["id"]}/verify')
    assert response.status_code == 503 and "isNormal" not in response.json()


def test_gateway_manifest_pin_and_transport(monkeypatch, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"deploymentId": "expected"}))
    monkeypatch.setattr(settings, "FABRIC_OBSERVATION_MANIFEST", str(path))
    monkeypatch.setattr(settings, "FABRIC_READER_TOKEN", "x" * 40)
    monkeypatch.setattr(FabricObservation, "request", lambda *args: {"deploymentId": "other"})
    with pytest.raises(ChainUnavailable):
        FabricObservation()
    monkeypatch.setattr(settings, "FABRIC_READER_URL", "http://external.example")
    with pytest.raises(ChainUnavailable):
        FabricObservation()


def test_worker_pins_deployment_and_keeps_bundle_for_uncertain_retry(fabric, monkeypatch):
    from app.services import fabric_observation as module
    from tests.unit.test_onchain import PROOF

    _, db, job, chain, response = fabric
    db.save_bundle(job, {"proof": PROOF, "publicSignals": ["0"]})
    job = db.capture(job["id"])
    monkeypatch.setattr(module, "FabricObservation", lambda **kwargs: chain)
    job["registry"] = "wrong"
    with pytest.raises(RuntimeError, match="pinned"):
        process_fabric_job(db, job)
    job["registry"] = "deployment"
    chain.request.side_effect = ChainUnavailable("timeout")
    with pytest.raises(ChainUnavailable):
        process_fabric_job(db, job)
    assert db.capture(job["id"])["bundle"] == job["bundle"]
    chain.request.side_effect = None
    chain.request.return_value = {"result": {**response, "status": "recorded"}, "commit": {"code": 0}}
    process_fabric_job(db, job)
    assert db.capture(job["id"])["status"] == "recorded"


def test_existing_catalog_migrates_to_evm_without_changing_records(context):
    from app.services.observation_store import ObservationStore

    client, db, headers = context
    capture = ingest(client, headers, db.add_patient()["id"]).json()["id"]
    db.update(capture, registry="original", tx_hash="original-transaction")
    with db.connect() as connection:
        connection.execute("ALTER TABLE captures DROP COLUMN ledger")
    migrated = ObservationStore().capture(capture)
    assert migrated["ledger"] == "evm"
    assert migrated["registry"] == "original"
    assert migrated["tx_hash"] == "original-transaction"
