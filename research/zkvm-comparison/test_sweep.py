import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).with_name("sweep.py")
SPEC = importlib.util.spec_from_file_location("zk_sweep", MODULE_PATH)
assert SPEC and SPEC.loader
sweep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sweep)


def test_parse_json_stdout_uses_last_json_line():
    parsed = sweep.parse_json_stdout(
        'loading\n{"old": true}\n{"proving_seconds": 1.25}\n'
    )

    assert parsed == {"proving_seconds": 1.25}


def test_profile_stage_returns_only_time_fields(monkeypatch):
    profile = {
        "execution_seconds": 0.2,
        "proving_seconds": 1.5,
        "verification_seconds": 0.1,
        "proof_stats": {"total_cycles": 999},
    }
    monkeypatch.setattr(
        sweep.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(profile),
            stderr="",
        ),
    )

    result = sweep.profile_stage("pca", Path("input.json"))

    assert result["status"] == "completed"
    assert result["guest_execution_seconds"] == 0.2
    assert result["prove_seconds"] == 1.5
    assert result["verify_seconds"] == 0.1
    assert "proof_stats" not in result


def test_cli_only_accepts_input_and_output():
    args = sweep.parse_args(
        ["--csi-file", "measurement.csi", "--output", "result.json"]
    )

    assert args.csi_file == Path("measurement.csi")
    assert args.output == Path("result.json")

    with pytest.raises(SystemExit):
        sweep.parse_args(
            [
                "--csi-file",
                "measurement.csi",
                "--output",
                "result.json",
                "--sizes",
                "64x3",
            ]
        )
