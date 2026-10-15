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
@pytest.mark.asyncio
async def test_generate_proof_returns_proof_bound_intermediate_hash(tmp_path):
    service = _service_without_setup()
    service.label = "Lomb_scargle_normality"
    service.circuit_name = service.CIRCUIT_NAME
    service.build_dir = tmp_path / "build"
    service.keys_dir = tmp_path / "keys"
    wasm_dir = service.build_dir / f"{service.circuit_name}_js"
    wasm_dir.mkdir(parents=True)
    service.keys_dir.mkdir(parents=True)
    (wasm_dir / f"{service.circuit_name}.wasm").write_bytes(b"wasm")
    (service.keys_dir / f"{service.circuit_name}_final.zkey").write_bytes(b"zkey")
    service._circuit_build_is_stale = lambda *_: False
    observed = {}

    async def generate(input_data, verify=False):
        observed.update(input_data)
        assert verify is True
        public_signals = ["1", "0", "40", "40", "67890"]
        public_signals.extend(str(value) for value in range(CIRCOM_SAMPLES))
        public_signals.append("777")
        return {}, public_signals, True, {}

    service._generate_proof_with_benchmark = generate
    service._performance_from_benchmark = lambda _: {}
    samples = [[1024] * CIRCOM_SAMPLES for _ in range(PCA_COMPONENTS)]
    result = await service.generate_proof(
        samples=samples,
        timestamps_ms=list(range(CIRCOM_SAMPLES)),
        parent_commitment="777",
    )

    assert 0 < observed["commitmentNonce"] < 2**128
    assert result["intermediateHash"]["value"] == "67890"
    assert result["intermediateHash"]["domainTag"] == 0x43534911
    assert result["parentCommitment"] == "777"
    assert observed["parentCommitment"] == "777"


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
