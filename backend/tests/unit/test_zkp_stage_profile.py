"""段階プロファイルによる証明生成時間の按分の契約。"""

import json

import pytest

from app.services.zkp_stage_profile import build_stage_breakdown

CIRCUIT = "csi_breathing_certificate"

PROFILE = {
    "circuitName": CIRCUIT,
    "totalConstraints": 1000,
    "fixedOverheadMs": 500.0,
    "measuredAt": "2026-08-31T00:00:00+00:00",
    "stages": [
        {"key": "a", "label": "段階A", "description": "説明A", "constraints": 750},
        {"key": "b", "label": "段階B", "description": "説明B", "constraints": 250},
    ],
}


def _write_profile(zkp_dir, profile=PROFILE):
    target = zkp_dir / "profiles"
    target.mkdir(parents=True, exist_ok=True)
    (target / "stage_profile.json").write_text(json.dumps(profile))


@pytest.mark.unit
def test_attributes_work_time_by_constraint_share(tmp_path):
    _write_profile(tmp_path)

    result = build_stage_breakdown(tmp_path, CIRCUIT, proof_generation_ms=900.0, constraint_count=1000)

    # 固定費を引いた 400ms が制約数比 750:250 で配分される
    assert result["fixedOverheadMs"] == 500.0
    assert result["attributedWorkMs"] == 400.0
    assert [s["estimatedMs"] for s in result["stages"]] == [300.0, 100.0]
    assert [s["label"] for s in result["stages"]] == ["段階A", "段階B"]


@pytest.mark.unit
def test_breakdown_sums_back_to_measured_total(tmp_path):
    _write_profile(tmp_path)

    measured = 837.5
    result = build_stage_breakdown(tmp_path, CIRCUIT, proof_generation_ms=measured, constraint_count=1000)

    total = sum(s["estimatedMs"] for s in result["stages"]) + result["fixedOverheadMs"]
    assert total == pytest.approx(measured, abs=0.01)


@pytest.mark.unit
def test_omits_breakdown_when_circuit_no_longer_matches_profile(tmp_path):
    """回路を再コンパイルして制約数が変わったら、古い按分は出さない。"""
    _write_profile(tmp_path)

    assert build_stage_breakdown(tmp_path, CIRCUIT, 900.0, constraint_count=2000) is None


@pytest.mark.unit
def test_omits_breakdown_without_profile(tmp_path):
    assert build_stage_breakdown(tmp_path, CIRCUIT, 900.0, constraint_count=1000) is None


@pytest.mark.unit
def test_omits_breakdown_for_other_circuit(tmp_path):
    _write_profile(tmp_path)

    assert build_stage_breakdown(tmp_path, "csi_lomb_scargle_normality", 900.0, 1000) is None


@pytest.mark.unit
def test_falls_back_when_measured_time_is_below_recorded_overhead(tmp_path):
    """別環境で測ったプロファイルなどで固定費を下回った場合は全体を按分対象にする。"""
    _write_profile(tmp_path)

    result = build_stage_breakdown(tmp_path, CIRCUIT, proof_generation_ms=400.0, constraint_count=1000)

    assert result["fixedOverheadMs"] == 0.0
    assert result["attributedWorkMs"] == 400.0
    assert sum(s["estimatedMs"] for s in result["stages"]) == pytest.approx(400.0, abs=0.01)
