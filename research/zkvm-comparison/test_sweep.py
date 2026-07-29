import importlib.util
import json
import math
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("sweep.py")
SPEC = importlib.util.spec_from_file_location("zk_sweep", MODULE_PATH)
assert SPEC and SPEC.loader
sweep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sweep)


def test_parse_sizes_preserves_order_and_removes_duplicates():
    assert sweep.parse_sizes("64x3,128x4,64x3") == [(64, 3), (128, 4)]


def test_flatten_profile_extracts_stage_cycles():
    row = sweep.flatten_record(
        {
            "samples": 64,
            "subcarriers": 3,
            "input_elements": 192,
            "stage": "pca",
            "status": "completed",
            "outer_wall_seconds": 12.0,
            "profile": {
                "execution_seconds": 0.2,
                "execution_user_cycles": 100,
                "proving_seconds": 10.0,
                "verification_seconds": 0.1,
                "proof_stats": {"total_cycles": 256, "user_cycles": 100, "segments": 1},
                "journal": {
                    "stage_cycles": [{"stage": "pca", "cycles": 75}],
                },
            },
        }
    )

    assert row["function_cycles"] == 75
    assert row["proving_seconds"] == 10.0
    assert math.isclose(row["total_execution_seconds"], 10.3)


def test_flatten_isolated_profile_extracts_proof_memory():
    row = sweep.flatten_record(
        {
            "samples": 300,
            "subcarriers": 8,
            "input_elements": 2400,
            "stage": "bandpass",
            "profile_mode": "isolated",
            "status": "completed",
            "outer_wall_seconds": 4.0,
            "memory": {
                "process_peak_rss_bytes": 900_000_000,
                "cgroup_memory_peak_during_bytes": 1_100_000_000,
            },
            "profile": {
                "host_dependency_prepare_seconds": 0.2,
                "request_input_elements": 2400,
                "proving_seconds": 3.5,
                "verification_seconds": 0.1,
                "proving_memory": {
                    "peak_rss_bytes": 800_000_000,
                    "peak_virtual_memory_bytes": 1_600_000_000,
                },
                "proof_stats": {"total_cycles": 512, "user_cycles": 400},
                "journal": {
                    "stage_cycles": [{"stage": "bandpass", "cycles": 300}],
                },
            },
        }
    )

    assert row["profile_mode"] == "isolated"
    assert row["function_cycles"] == 300
    assert row["host_prepare_seconds"] == 0.2
    assert row["request_input_elements"] == 2400
    assert row["proving_peak_rss_bytes"] == 800_000_000
    assert row["process_peak_rss_bytes"] == 900_000_000
    assert math.isclose(row["total_execution_seconds"], 3.6)


def test_detailed_process_rows_only_use_full_profile():
    rows = sweep.detailed_process_rows(
        {
            "records": [
                {
                    "samples": 64,
                    "subcarriers": 3,
                    "input_elements": 192,
                    "stage": "full",
                    "status": "completed",
                    "profile": {
                        "journal": {
                            "process_cycles": [
                                {
                                    "process": "commitment_hash",
                                    "calls": 1,
                                    "inclusive_cycles": 50,
                                    "exclusive_cycles": 50,
                                }
                            ]
                        }
                    },
                },
                {
                    "samples": 64,
                    "subcarriers": 3,
                    "input_elements": 192,
                    "stage": "pca",
                    "status": "completed",
                    "profile": {"journal": {"process_cycles": []}},
                },
            ]
        }
    )

    assert rows == [
        {
            "samples": 64,
            "subcarriers": 3,
            "input_elements": 192,
            "stage": "commitment_hash",
            "status": "completed",
            "calls": 1,
            "inclusive_cycles": 50,
            "exclusive_cycles": 50,
            "function_cycles": 50,
        }
    ]


def test_write_measured_results_records_json_csv_svg_output_time(tmp_path):
    output = tmp_path / "scale.json"
    payload = {"records": [], "timings": {}}

    sweep.write_measured_results(payload, output)
    saved = json.loads(output.read_text(encoding="utf-8"))

    assert saved["timings"]["result_output_seconds"] >= 0
    assert saved["timings"]["result_output_measurements"] == 1
    assert output.with_suffix(".csv").is_file()
