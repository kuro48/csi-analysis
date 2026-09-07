"""Lomb--Scargle Circomサービスの入力契約。"""

import os

import pytest

from app.services.lomb_scargle_certificate_service import LombScargleCertificateService
from app.services.lomb_scargle_pipeline import CIRCOM_SAMPLES, PCA_COMPONENTS


def _service_without_setup() -> LombScargleCertificateService:
    return object.__new__(LombScargleCertificateService)


@pytest.mark.unit
def test_prepare_input_accepts_fixed_point_samples_and_timestamps():
    samples = [[1024] * CIRCOM_SAMPLES for _ in range(PCA_COMPONENTS)]
    timestamps_ms = list(range(CIRCOM_SAMPLES))

    result = _service_without_setup()._prepare_input(samples, timestamps_ms)

    assert result == {"samples": samples, "timestampsMs": timestamps_ms}


@pytest.mark.unit
@pytest.mark.parametrize("value", [-1, 2**11])
def test_prepare_input_rejects_out_of_range_value(value):
    samples = [[1024] * CIRCOM_SAMPLES for _ in range(PCA_COMPONENTS)]
    samples[0][0] = value

    with pytest.raises(ValueError, match="範囲外"):
        _service_without_setup()._prepare_input(samples, list(range(CIRCOM_SAMPLES)))


@pytest.mark.unit
def test_prepare_input_rejects_wrong_shape():
    with pytest.raises(ValueError):
        _service_without_setup()._prepare_input(
            [[1024] * CIRCOM_SAMPLES],
            list(range(CIRCOM_SAMPLES)),
        )


@pytest.mark.unit
def test_prepare_input_rejects_timestamp_out_of_range():
    timestamps_ms = list(range(CIRCOM_SAMPLES))
    timestamps_ms[-1] = 2**24
    with pytest.raises(ValueError, match="24-bit"):
        _service_without_setup()._prepare_input([[1024] * CIRCOM_SAMPLES for _ in range(PCA_COMPONENTS)], timestamps_ms)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_proof_rejects_stale_artifacts(tmp_path):
    circuit_name = LombScargleCertificateService.CIRCUIT_NAME
    circuit_dir = tmp_path / "circuits"
    wasm_dir = tmp_path / "build" / f"{circuit_name}_js"
    keys_dir = tmp_path / "keys"
    circuit_dir.mkdir(parents=True)
    wasm_dir.mkdir(parents=True)
    keys_dir.mkdir(parents=True)

    circuit = circuit_dir / f"{circuit_name}.circom"
    wasm = wasm_dir / f"{circuit_name}.wasm"
    r1cs = tmp_path / "build" / f"{circuit_name}.r1cs"
    zkey = keys_dir / f"{circuit_name}_final.zkey"
    circuit.write_text("pragma circom 2.0.0;\n")
    for artifact in (wasm, r1cs, zkey):
        artifact.write_bytes(b"old")

    for artifact in (wasm, r1cs, zkey):
        os.utime(artifact, ns=(1_000_000_000, 1_000_000_000))
    os.utime(circuit, ns=(2_000_000_000, 2_000_000_000))

    service = LombScargleCertificateService(zkp_dir=str(tmp_path), auto_compile=False)
    with pytest.raises(RuntimeError, match="stale"):
        await service.generate_proof(
            samples=[[1024] * CIRCOM_SAMPLES for _ in range(PCA_COMPONENTS)],
            timestamps_ms=list(range(CIRCOM_SAMPLES)),
        )
