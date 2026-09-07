"""Circom source and compiled-artifact freshness checks."""

import os

from app.services.zkp_circuit_service import ZKPCircuitService


def _service(zkp_dir, circuit_name="test_circuit"):
    service = object.__new__(ZKPCircuitService)
    service.circuit_name = circuit_name
    service.zkp_dir = zkp_dir
    service.build_dir = zkp_dir / "build"
    service.keys_dir = zkp_dir / "keys"
    return service


def _write_artifacts(service):
    wasm = service.build_dir / f"{service.circuit_name}_js" / f"{service.circuit_name}.wasm"
    r1cs = service.build_dir / f"{service.circuit_name}.r1cs"
    zkey = service.keys_dir / f"{service.circuit_name}_final.zkey"
    wasm.parent.mkdir(parents=True)
    zkey.parent.mkdir(parents=True)
    for artifact in (wasm, r1cs, zkey):
        artifact.write_bytes(b"artifact")
    return wasm, r1cs, zkey


def test_build_is_stale_when_included_circuit_is_newer(tmp_path):
    service = _service(tmp_path)
    circuits = tmp_path / "circuits"
    circuits.mkdir()
    main = circuits / "test_circuit.circom"
    dependency = circuits / "basis.circom"
    main.write_text('pragma circom 2.0.0;\ninclude "basis.circom";\n')
    dependency.write_text("template Basis() {}\n")
    wasm, r1cs, zkey = _write_artifacts(service)

    for path in (main, dependency):
        os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    for path in (wasm, r1cs, zkey):
        os.utime(path, ns=(2_000_000_000, 2_000_000_000))
    assert service._circuit_build_is_stale(wasm, zkey) is False

    os.utime(dependency, ns=(3_000_000_000, 3_000_000_000))
    assert service._circuit_build_is_stale(wasm, zkey) is True


def test_build_is_stale_when_r1cs_is_missing(tmp_path):
    service = _service(tmp_path)
    circuits = tmp_path / "circuits"
    circuits.mkdir()
    (circuits / "test_circuit.circom").write_text("pragma circom 2.0.0;\n")
    wasm, r1cs, zkey = _write_artifacts(service)
    r1cs.unlink()

    assert service._circuit_build_is_stale(wasm, zkey) is True


def test_ptau_trims_leftovers_from_an_interrupted_download(tmp_path):
    service = _service(tmp_path)
    service.keys_dir.mkdir(parents=True)
    ptau = service.keys_dir / "powersOfTau28_hez_final_24.ptau"
    ptau.write_bytes(b"x" * 100)

    assert service._ptau_is_complete(ptau, 64) is True
    assert ptau.stat().st_size == 64


def test_ptau_leaves_an_in_flight_download_alone(tmp_path):
    service = _service(tmp_path)
    service.keys_dir.mkdir(parents=True)
    ptau = service.keys_dir / "powersOfTau28_hez_final_24.ptau"
    ptau.write_bytes(b"x" * 100)
    ptau.with_name(ptau.name + ".aria2").write_bytes(b"control")

    assert service._ptau_is_complete(ptau, 64) is False
    assert ptau.stat().st_size == 100


def test_ptau_is_incomplete_when_short_or_missing(tmp_path):
    service = _service(tmp_path)
    service.keys_dir.mkdir(parents=True)
    short = service.keys_dir / "short.ptau"
    short.write_bytes(b"x" * 32)

    assert service._ptau_is_complete(short, 64) is False
    assert service._ptau_is_complete(service.keys_dir / "missing.ptau", 64) is False


def test_node_heap_is_larger_for_the_lomb_scargle_circuit(tmp_path, monkeypatch):
    monkeypatch.delenv("ZKP_NODE_MAX_OLD_SPACE_MB", raising=False)

    small = _service(tmp_path)
    large = _service(tmp_path, circuit_name="csi_lomb_scargle_normality")

    assert small._node_env()["NODE_OPTIONS"] == "--max-old-space-size=4096"
    assert large._node_env()["NODE_OPTIONS"] == "--max-old-space-size=12288"


def test_node_heap_can_be_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("ZKP_NODE_MAX_OLD_SPACE_MB", "8192")
    service = _service(tmp_path, circuit_name="csi_lomb_scargle_normality")

    assert service._node_env()["NODE_OPTIONS"] == "--max-old-space-size=8192"
