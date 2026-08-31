"""`.r1cs` ヘッダから回路メトリクスを読む処理の契約。"""

import struct

import pytest

from app.services.zkp_circuit_metrics import R1CS_MAGIC, read_r1cs_metrics
from tests.unit.r1cs_fixture import build_r1cs_bytes


@pytest.mark.unit
def test_reads_constraint_count_from_header_section(tmp_path):
    r1cs = tmp_path / "circuit.r1cs"
    r1cs.write_bytes(build_r1cs_bytes())

    metrics = read_r1cs_metrics(r1cs)

    assert metrics == {
        "constraint_count": 11354,
        "wire_count": 13049,
        "public_output_count": 1,
        "public_input_count": 0,
        "private_input_count": 1805,
        "label_count": 14169,
    }


@pytest.mark.unit
def test_skips_sections_before_the_header_section(tmp_path):
    r1cs = tmp_path / "circuit_with_leading_section.r1cs"
    r1cs.write_bytes(build_r1cs_bytes(constraint_count=6632, leading_section=True))

    metrics = read_r1cs_metrics(r1cs)

    assert metrics is not None
    assert metrics["constraint_count"] == 6632


@pytest.mark.unit
def test_returns_none_when_file_is_missing(tmp_path):
    assert read_r1cs_metrics(tmp_path / "absent.r1cs") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        b"nope" + struct.pack("<II", 1, 1),  # マジックが違う
        R1CS_MAGIC + struct.pack("<II", 1, 1),  # セクションが途中で切れている
    ],
)
def test_returns_none_for_unreadable_file(tmp_path, payload):
    r1cs = tmp_path / "broken.r1cs"
    r1cs.write_bytes(payload)

    assert read_r1cs_metrics(r1cs) is None


@pytest.mark.unit
def test_returned_metrics_are_not_shared_between_calls(tmp_path):
    r1cs = tmp_path / "circuit.r1cs"
    r1cs.write_bytes(build_r1cs_bytes())

    first = read_r1cs_metrics(r1cs)
    assert first is not None
    first["constraint_count"] = -1

    second = read_r1cs_metrics(r1cs)
    assert second is not None
    assert second["constraint_count"] == 11354
