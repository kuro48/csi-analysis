"""Circom証明時間ベンチマークとCSV出力の契約。"""

import asyncio
import csv
import io
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.endpoints.csi_data import build_circom_benchmark_csv
from app.models.csi_data import CSIData
from app.services.zkp_circuit_service import ZKPCircuitService


class _MeasuredCircuit(ZKPCircuitService):
    def __init__(self, zkp_dir: str = "/nonexistent") -> None:
        self.circuit_name = "test_circuit"
        self.label = "Test"
        # 段階プロファイルの探索基点。存在しないパスなら内訳は付かない。
        self.zkp_dir = Path(zkp_dir)

    def _get_constraint_count(self):
        return 4

    async def _generate_witness(self, input_data):
        await asyncio.sleep(0.001)
        return "witness.wtns"

    async def _generate_groth16_proof(self, witness_file):
        await asyncio.sleep(0.001)
        return {"pi_a": ["1"]}, ["1"]

    async def verify_proof(self, proof, public_signals):
        await asyncio.sleep(0.001)
        return True


@pytest.mark.unit
def test_reads_and_caches_constraint_count_from_snarkjs_info(monkeypatch, tmp_path):
    service = object.__new__(ZKPCircuitService)
    service.circuit_name = "test_circuit"
    service.label = "Test"
    service.build_dir = tmp_path
    service.zkp_dir = tmp_path
    (tmp_path / "test_circuit.r1cs").write_bytes(b"r1cs")
    service._constraint_count_cache.clear()
    calls = []

    monkeypatch.setattr("app.services.zkp_circuit_service.shutil.which", lambda _: "/usr/bin/snarkjs")

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="[INFO] # of Constraints: 9,201", stderr="")

    monkeypatch.setattr("app.services.zkp_circuit_service.subprocess.run", fake_run)

    assert service._get_constraint_count() == 9201
    assert service._get_constraint_count() == 9201
    assert len(calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_records_each_proving_phase_and_per_constraint_average():
    _, _, is_valid, benchmark = await _MeasuredCircuit()._generate_proof_with_benchmark({"input": [1]}, verify=True)

    assert is_valid is True
    assert benchmark["circuitName"] == "test_circuit"
    assert benchmark["constraintCount"] == 4
    assert benchmark["witnessGenerationMs"] > 0
    assert benchmark["proofGenerationMs"] > 0
    assert benchmark["verificationMs"] > 0
    assert benchmark["totalMs"] == pytest.approx(
        benchmark["witnessGenerationMs"] + benchmark["proofGenerationMs"] + benchmark["verificationMs"],
        abs=0.002,
    )
    assert benchmark["averageProofTimePerConstraintNs"] == pytest.approx(
        benchmark["proofGenerationMs"] * 1_000_000 / 4,
        rel=0.01,
    )


@pytest.mark.unit
def test_csv_contains_the_same_benchmark_values_as_processed_data():
    csi_data_id = uuid.uuid4()
    benchmark = {
        "circuitName": "csi_breathing_certificate",
        "provingSystem": "groth16",
        "curve": "bn128",
        "constraintCount": 9201,
        "witnessGenerationMs": 100.125,
        "proofGenerationMs": 250.5,
        "verificationMs": 15.25,
        "totalMs": 365.875,
        "averageProofTimePerConstraintNs": 27225.302,
        "measuredAt": "2026-08-30T12:00:00+00:00",
    }
    processed_data = {
        "proofs": {
            "python_circom": {
                "status": "completed",
                "method": "breathing_certificate",
                "benchmark": benchmark,
            }
        }
    }

    csv_text = build_circom_benchmark_csv(csi_data_id, processed_data)
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert len(rows) == 1
    assert rows[0]["csi_data_id"] == str(csi_data_id)
    assert rows[0]["circuit_name"] == "csi_breathing_certificate"
    assert rows[0]["constraint_count"] == "9201"
    assert rows[0]["proof_generation_ms"] == "250.5"
    assert rows[0]["average_proof_time_per_constraint_ns"] == "27225.302"


@pytest.mark.unit
def test_csv_rejects_records_without_benchmarks():
    with pytest.raises(ValueError, match="計測結果がありません"):
        build_circom_benchmark_csv(uuid.uuid4(), {"proofs": {}})


@pytest.mark.unit
def test_saved_benchmark_can_be_downloaded_from_csv_endpoint(client, db):
    record = CSIData(
        status="completed",
        processed_data={
            "proofs": {
                "python_circom": {
                    "status": "completed",
                    "method": "breathing_certificate",
                    "benchmark": {
                        "circuitName": "csi_breathing_certificate",
                        "provingSystem": "groth16",
                        "curve": "bn128",
                        "constraintCount": 9201,
                        "witnessGenerationMs": 100.0,
                        "proofGenerationMs": 250.0,
                        "verificationMs": 15.0,
                        "totalMs": 365.0,
                        "averageProofTimePerConstraintNs": 27170.96,
                        "measuredAt": "2026-08-30T12:00:00+00:00",
                    },
                }
            }
        },
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    response = client.get(f"/api/v2/csi-data/{record.id}/circom-benchmarks.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "csi_breathing_certificate" in response.text
