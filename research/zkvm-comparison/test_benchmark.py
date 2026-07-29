import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("benchmark.py")
SPEC = importlib.util.spec_from_file_location("zk_benchmark", MODULE_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_atomic_write_json(tmp_path):
    output = tmp_path / "result.json"

    benchmark.atomic_write_json(output, {"status": "completed"})

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "status": "completed"
    }
    assert not output.with_suffix(".json.tmp").exists()


def test_cli_only_accepts_input_and_output():
    args = benchmark.parse_args(
        ["--csi-file", "measurement.csi", "--output", "result.json"]
    )

    assert args.csi_file == Path("measurement.csi")
    assert args.output == Path("result.json")

    with pytest.raises(SystemExit):
        benchmark.parse_args(
            [
                "--csi-file",
                "measurement.csi",
                "--output",
                "result.json",
                "--runs",
                "3",
            ]
        )
