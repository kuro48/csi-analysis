import asyncio
import csv
import json

import pytest

from app.services.hybrid_experiment_service import HybridExperimentService


class _Committed:
    async def generate_proof(self, **kwargs):
        return {
            "proof": {"pi_a": ["1"]},
            "isValid": True,
            "isNormal": True,
            "commitment": {"value": "12"},
            "benchmark": {
                "witnessGenerationMs": 10,
                "proofGenerationMs": 20,
                "verificationMs": 2,
                "totalMs": 32,
                "constraintCount": 100,
            },
        }


class _Approx:
    async def generate_proof(self, **kwargs):
        assert kwargs["parent_commitment"] == "555"
        return {
            "proof": {"pi_a": ["2"]},
            "estimatedBpm": 14.0,
            "isValid": True,
            "isNormal": True,
            "parentCommitment": "555",
            "chainLinked": True,
            "benchmark": {"totalMs": 40, "constraintCount": 200},
        }


class _Preprocess:
    async def generate_proof(self, **kwargs):
        return {
            "proof": {"pi_a": ["3"]},
            "isValid": True,
            "projectionCommitment": {"value": "555"},
            "benchmark": {"totalMs": 50, "constraintCount": 300},
        }


def _pipeline(_path, include_preprocess_projection_input=False):
    assert include_preprocess_projection_input is True
    return {
        "breathing_rate_bpm": 15.0,
        "certificate_input": {"vmdInput": [1], "modes": [[1]] * 5, "sel": [1, 0, 0, 0, 0]},
        "vmd_approx_input": {"waveform": [0] * 128},
        "preprocess_projection_input": {
            "centeredX": [[0] * 8 for _ in range(32)],
            "weights": [0] * 8,
            "projected": [0] * 32,
            "diagnostics": {"reference_correlation": 0.9},
        },
        "n_samples": 100,
        "n_subcarriers_total": 16,
        "n_subcarriers_selected": 8,
    }


@pytest.mark.unit
def test_experiment_writes_jsonl_and_method_csv(tmp_path):
    capture = tmp_path / "capture.csi"
    capture.write_bytes(b"same-capture")
    results = tmp_path / "results"
    service = HybridExperimentService(
        pipeline_runner=_pipeline,
        committed_factory=_Committed,
        approx_factory=_Approx,
        preprocess_factory=_Preprocess,
        results_dir=str(results),
    )

    record = asyncio.run(
        service.run(str(capture), ground_truth_bpm=15.0, dataset_id="subject-1", source_filename=capture.name)
    )

    assert [row["method"] for row in record["methods"]] == [
        "python_baseline",
        "python_circom_committed",
        "circom_preprocess_projection",
        "circom_vmd_approx",
    ]
    assert record["methods"][0]["absolute_error_bpm"] == 0
    assert record["methods"][3]["absolute_error_bpm"] == 1
    assert len((results / "runs.jsonl").read_text().splitlines()) == 1
    assert json.loads((results / "runs.jsonl").read_text())["dataset_id"] == "subject-1"
    with (results / "method_runs.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4
    assert {row["experiment_id"] for row in rows} == {record["experiment_id"]}
    assert {row["dataset_id"] for row in rows} == {"subject-1"}
