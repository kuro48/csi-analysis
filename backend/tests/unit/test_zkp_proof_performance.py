"""各回路の証明生成が制約数と所要時間を返す契約。"""

import asyncio
import json

import pytest

from app.services.breathing_certificate_service import BreathingCertificateService
from app.services.lomb_scargle_certificate_service import LombScargleCertificateService
from app.services.lomb_scargle_pipeline import N_FREQUENCIES, PCA_COMPONENTS
from tests.unit.r1cs_fixture import build_r1cs_bytes

CONSTRAINT_COUNT = 11354


def _prepare_circuit_files(zkp_dir, circuit_name: str) -> None:
    """コンパイル済み回路が揃っている状態を tmp_path 上に作る。"""
    build_dir = zkp_dir / "build"
    keys_dir = zkp_dir / "keys"
    (build_dir / f"{circuit_name}_js").mkdir(parents=True, exist_ok=True)
    keys_dir.mkdir(parents=True, exist_ok=True)

    (build_dir / f"{circuit_name}_js" / f"{circuit_name}.wasm").write_bytes(b"wasm")
    (keys_dir / f"{circuit_name}_final.zkey").write_bytes(b"zkey")
    (build_dir / f"{circuit_name}.r1cs").write_bytes(build_r1cs_bytes(constraint_count=CONSTRAINT_COUNT))


def _stub_proof_steps(service, public_signals) -> None:
    """witness / prove / verify を、計測できる程度の待ち時間を持つ偽実装に差し替える。"""

    async def fake_witness(_input_data):
        await asyncio.sleep(0.01)
        return "witness.wtns"

    async def fake_prove(_witness_file):
        await asyncio.sleep(0.01)
        return {"pi_a": ["1"]}, list(public_signals)

    async def fake_verify(_proof, _public_signals):
        await asyncio.sleep(0.01)
        return True

    service._generate_witness = fake_witness
    service._generate_groth16_proof = fake_prove
    service.verify_proof = fake_verify


def _assert_timing_contract(performance) -> None:
    for key in ("witness_time_seconds", "prove_time_seconds", "verify_time_seconds"):
        assert performance[key] > 0, f"{key} が計測されていません"
    assert performance["generation_time_seconds"] == pytest.approx(
        performance["witness_time_seconds"] + performance["prove_time_seconds"]
    )
    # 証明生成時間に検証時間を混ぜない
    assert performance["generation_time_seconds"] < (
        performance["witness_time_seconds"] + performance["prove_time_seconds"] + performance["verify_time_seconds"]
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_breathing_certificate_proof_reports_constraints_and_times(tmp_path):
    _prepare_circuit_files(tmp_path, BreathingCertificateService.CIRCUIT_NAME)
    service = BreathingCertificateService(zkp_dir=str(tmp_path), auto_compile=False)
    _stub_proof_steps(service, ["1"])

    result = await service.generate_proof(
        vmd_input=[1, 2, 1],
        modes=[[1, 2, 1]] * BreathingCertificateService.K,
        sel=[1, 0, 0, 0, 0],
    )

    performance = result["performance"]
    assert performance["circuit_name"] == BreathingCertificateService.CIRCUIT_NAME
    assert performance["constraint_count"] == CONSTRAINT_COUNT
    _assert_timing_contract(performance)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lomb_scargle_proof_reports_constraints_and_times(tmp_path):
    _prepare_circuit_files(tmp_path, LombScargleCertificateService.CIRCUIT_NAME)
    service = LombScargleCertificateService(zkp_dir=str(tmp_path), auto_compile=False)
    _stub_proof_steps(service, ["1", "2", "40", "40"])

    result = await service.generate_proof(powers=[[0] * N_FREQUENCIES for _ in range(PCA_COMPONENTS)])

    performance = result["performance"]
    assert performance["circuit_name"] == LombScargleCertificateService.CIRCUIT_NAME
    assert performance["constraint_count"] == CONSTRAINT_COUNT
    _assert_timing_contract(performance)


@pytest.mark.unit
def test_circuit_metrics_fall_back_to_circuit_name_without_r1cs(tmp_path):
    _prepare_circuit_files(tmp_path, BreathingCertificateService.CIRCUIT_NAME)
    (tmp_path / "build" / f"{BreathingCertificateService.CIRCUIT_NAME}.r1cs").unlink()
    service = BreathingCertificateService(zkp_dir=str(tmp_path), auto_compile=False)

    assert service.circuit_metrics() == {"circuit_name": BreathingCertificateService.CIRCUIT_NAME}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zkvm_proof_reports_generation_time(tmp_path, monkeypatch):
    from app.services.zkvm_service import ZkVMBreathingService

    binary = tmp_path / "csi-zkvm-host"
    binary.write_text("binary")
    binary.chmod(0o755)

    class _Process:
        returncode = 0

        async def communicate(self):
            await asyncio.sleep(0.01)
            output = {
                "receipt": "receipt-data",
                "journal": {"input_commitment": "commitment-1", "is_normal": True},
                "isNormal": True,
                "isValid": True,
                "method": "risc0_5_1_fixed_v1",
            }
            return json.dumps(output).encode(), b""

    async def _create_process(*_args, **_kwargs):
        return _Process()

    monkeypatch.setattr("asyncio.create_subprocess_exec", _create_process)
    service = ZkVMBreathingService(binary_path=binary, timeout_seconds=2)

    result = await service.generate_proof(
        {"samples": 1, "subcarriers": 1, "amplitudes": [1], "scale": 100, "input_commitment": "commitment-1"}
    )

    performance = result["performance"]
    assert performance["proof_system"] == "risc0_zkvm"
    assert performance["generation_time_seconds"] > 0
    # zkVM に Circom 相当の制約数は存在しない
    assert "constraint_count" not in performance


@pytest.mark.unit
def test_normalized_proof_result_keeps_performance():
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    normalized = VerifiableBreathingService._normalize_result(
        {"isValid": True, "performance": {"constraint_count": 42, "generation_time_seconds": 1.5}}
    )

    assert normalized["status"] == "completed"
    assert normalized["performance"] == {"constraint_count": 42, "generation_time_seconds": 1.5}
