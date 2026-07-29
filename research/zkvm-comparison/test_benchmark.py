import importlib.util
import json
import math
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("benchmark.py")
SPEC = importlib.util.spec_from_file_location("zk_benchmark", MODULE_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_summarize_runs_reports_median_and_p95():
    summary = benchmark.summarize_runs(
        [
            {"total_execution_seconds": 1.0, "ignored": 100},
            {"total_execution_seconds": 2.0, "ignored": 200},
            {"total_execution_seconds": 9.0, "ignored": 300},
        ]
    )

    assert set(summary) == {"total_execution_seconds"}
    assert summary["total_execution_seconds"]["count"] == 3
    assert summary["total_execution_seconds"]["median"] == 2.0
    assert math.isclose(summary["total_execution_seconds"]["p95"], 8.3)


def test_percentile_handles_single_value():
    assert benchmark.percentile([3.25], 0.95) == 3.25


def test_write_timed_json_records_output_time(tmp_path):
    output = tmp_path / "result.json"
    payload = {"status": "completed"}

    benchmark.write_timed_json(output, payload)
    saved = json.loads(output.read_text(encoding="utf-8"))

    assert saved["result_output_seconds"] >= 0
    assert saved["result_output_metadata_rewrite_excluded"] is True
