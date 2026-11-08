import json
from unittest.mock import Mock

import numpy as np
import pytest

from app.api.endpoints import observations
from app.core.config import settings
from app.services.adaptive_csi_input import canonicalize_all_columns
from app.services.observation_protocol import validate_protocol
from app.services.observation_store import ObservationStore
from app.services.onchain_service import ChainUnavailable
from tests.unit.test_observations import context, ingest  # noqa: F401

PROTOCOL = {"circuit": "csi_lomb_scargle_adaptive_4004", "publicSignalCount": 70, "isNormalIndex": 1}


def test_preserves_all_4004_columns_and_shared_quantization():
    matrix = np.tile(np.arange(1, 4005, dtype=float), (64, 1)).astype(complex)
    matrix[31, 4003] += 3000j
    data, metadata = canonicalize_all_columns(matrix, np.arange(64) * 1_000_000_000)
    expected_i = np.rint(matrix.real * (1800 / 4004)).astype(int) + 2048
    expected_q = np.rint(matrix.imag * (1800 / 4004)).astype(int) + 2048
    assert data["csiI"] == expected_i.tolist()
    assert data["csiQ"] == expected_q.tolist()
    assert data["candidateCount"] == 4004
    assert metadata["columnSelection"] == "all-columns-in-parser-order"
    assert data["timestampsMs"] == list(range(0, 64000, 1000))


def test_sorts_time_and_adds_canonical_padding_without_ranking():
    matrix = np.arange(64 * 3).reshape(64, 3).astype(complex) + 1
    times = np.arange(64) * 1_000_000
    a, _ = canonicalize_all_columns(matrix, times, 4)
    b, _ = canonicalize_all_columns(matrix[::-1], times[::-1], 4)
    assert a["csiI"] == b["csiI"]
    assert a["candidateCount"] == 3
    assert all(row[3] == 2048 for row in a["csiI"] + a["csiQ"])


@pytest.mark.parametrize("kind", ["overflow", "duplicates", "nonfinite", "zero", "shape"])
def test_rejects_invalid_capture_without_silent_fallback(kind):
    matrix = np.ones((64, 4), dtype=complex)
    times = np.arange(64) * 1_000_000
    capacity = 4
    if kind == "overflow":
        capacity = 3
    elif kind == "duplicates":
        times[1] = times[0]
    elif kind == "nonfinite":
        matrix[3, 1] = np.nan
    elif kind == "zero":
        matrix[:] = 0
    else:
        times = times[:-1]
    with pytest.raises(ValueError, match="adaptive_"):
        canonicalize_all_columns(matrix, times, capacity)


@pytest.fixture
def configured(context, monkeypatch, tmp_path):
    manifest = tmp_path / "adaptive.json"
    manifest.write_text(json.dumps(PROTOCOL))
    monkeypatch.setattr(settings, "ADAPTIVE_FABRIC_MANIFEST", str(manifest))
    monkeypatch.setattr(settings, "ADAPTIVE_OBSERVATION_MANIFEST", str(manifest))
    return context


def test_capture_pins_profile_and_refuses_profile_change_on_retry(configured):
    client, db, headers = configured
    patient = db.add_patient()["id"]
    assert client.get("/observations/capabilities").json()["adaptive4004"] == {"evm": True, "fabric": True}
    reply = ingest(client, headers, patient, proof_profile="adaptive4004", ledger="fabric")
    assert reply.status_code == 202
    job = db.capture(reply.json()["id"])
    assert job["proof_profile"] == "adaptive4004"
    assert ingest(client, headers, patient, job["id"], ledger="fabric", proof_profile="legacy").status_code == 409
    assert ingest(client, headers, patient, proof_profile="unknown").status_code == 422
    public = client.get(f"/observations/patients/{patient}/measurements").json()
    assert public["measurements"][0]["proof_profile"] == "adaptive4004"
    assert "isNormal" not in client.post(f'/observations/measurements/{job["id"]}/verify').json()


def test_unconfigured_adaptive_is_not_accepted(context, monkeypatch):
    client, db, headers = context
    monkeypatch.setattr(settings, "ADAPTIVE_FABRIC_MANIFEST", "")
    assert client.get("/observations/capabilities").json()["adaptive4004"]["fabric"] is False
    assert (
        ingest(client, headers, db.add_patient()["id"], ledger="fabric", proof_profile="adaptive4004").status_code
        == 503
    )
    assert not list(db.raw.iterdir())


@pytest.mark.parametrize("ledger", ["fabric", "evm"])
def test_verification_routes_to_the_pinned_adaptive_profile(configured, monkeypatch, ledger):
    client, db, headers = configured
    patient = db.add_patient()["id"]
    capture = ingest(client, headers, patient, proof_profile="adaptive4004", ledger=ledger).json()["id"]
    db.update(capture, tx_hash="transaction", status="recorded")
    chain = Mock()
    chain.result.return_value = {"status": "verified", "isNormal": False}
    factory = Mock(return_value=chain)
    monkeypatch.setattr(observations, "FabricObservation" if ledger == "fabric" else "ObservationChain", factory)
    reply = client.post(f"/observations/measurements/{capture}/verify")
    assert reply.status_code == 200 and reply.json()["isNormal"] is False
    if ledger == "fabric":
        factory.assert_called_once_with(profile="adaptive4004")
    else:
        factory.assert_called_once_with("adaptive4004")
    chain.result.side_effect = ChainUnavailable("unavailable")
    failed = client.post(f"/observations/measurements/{capture}/verify")
    assert failed.status_code == 503 and "isNormal" not in failed.json()


def test_existing_rows_migrate_as_legacy(context):
    client, db, headers = context
    capture = ingest(client, headers, db.add_patient()["id"]).json()["id"]
    with db.connect() as connection:
        connection.execute("ALTER TABLE captures DROP COLUMN proof_profile")
    assert ObservationStore().capture(capture)["proof_profile"] == "legacy"


def test_mixed_protocols_fail_closed():
    assert validate_protocol(PROTOCOL, "adaptive4004") == (70, 1)
    with pytest.raises(ValueError):
        validate_protocol(PROTOCOL, "legacy")
    with pytest.raises(ValueError):
        validate_protocol({**PROTOCOL, "isNormalIndex": 0}, "adaptive4004")
