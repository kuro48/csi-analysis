"""RISC Zero ホスト CLI アダプタの単体テスト。"""

import json
from pathlib import Path

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zkvm_service_invokes_prover_and_validates_commitment(tmp_path, monkeypatch):
    from app.services.zkvm_service import ZkVMBreathingService

    binary = tmp_path / "csi-zkvm-host"
    binary.write_text("binary")
    binary.chmod(0o755)
    observed = {}

    class _Process:
        returncode = 0

        async def communicate(self):
            request_path = Path(observed["args"][-1])
            request = json.loads(request_path.read_text())
            output = {
                "receipt": "receipt-data",
                "journal": {
                    "input_commitment": request["input_commitment"],
                    "is_normal": True,
                },
                "isNormal": True,
                "isValid": True,
                "method": "risc0_5_1_fixed_v1",
            }
            return json.dumps(output).encode(), b""

    async def _create_process(*args, **kwargs):
        observed["args"] = args
        return _Process()

    monkeypatch.setattr("asyncio.create_subprocess_exec", _create_process)
    service = ZkVMBreathingService(binary_path=binary, timeout_seconds=2)
    pipeline_input = {
        "samples": 2,
        "subcarriers": 2,
        "amplitudes": [1, 2, 3, 4],
        "scale": 100,
        "input_commitment": "commitment-1",
    }

    result = await service.generate_proof(pipeline_input)

    assert observed["args"][0] == str(binary)
    assert observed["args"][1] == "prove"
    assert result["journal"]["input_commitment"] == "commitment-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zkvm_service_rejects_mismatched_public_commitment(tmp_path, monkeypatch):
    from app.services.zkvm_service import ZkVMBreathingService

    binary = tmp_path / "csi-zkvm-host"
    binary.write_text("binary")
    binary.chmod(0o755)

    class _Process:
        returncode = 0

        async def communicate(self):
            output = {
                "receipt": "receipt-data",
                "journal": {"input_commitment": "different"},
            }
            return json.dumps(output).encode(), b""

    async def _create_process(*args, **kwargs):
        return _Process()

    monkeypatch.setattr("asyncio.create_subprocess_exec", _create_process)
    service = ZkVMBreathingService(binary_path=binary, timeout_seconds=2)

    with pytest.raises(RuntimeError, match="commitment"):
        await service.generate_proof(
            {
                "samples": 1,
                "subcarriers": 1,
                "amplitudes": [1],
                "scale": 100,
                "input_commitment": "expected",
            }
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zkvm_service_reports_missing_binary(tmp_path):
    from app.services.zkvm_service import ZkVMBreathingService

    service = ZkVMBreathingService(binary_path=tmp_path / "missing")

    with pytest.raises(FileNotFoundError, match="zkVM prover binary"):
        await service.generate_proof({"input_commitment": "x"})
