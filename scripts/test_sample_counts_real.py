"""Checks preparation and arithmetic bounds; no synthetic CSI performance data."""
import pytest
from evaluate_sample_counts import COUNTS, FR, ROOT, read


@pytest.fixture(scope="module")
def prepared():
    work = ROOT / ".local/sample-count"
    if not (work / "datasets.json").exists():
        pytest.skip("Prepare existing real CSI captures before running this integration check")
    return work, read(work / "datasets.json")


def test_integer_comparison_bounds_for_extended_shapes():
    # Conservative bounds derived from the constrained input ranges, not generated CSI.
    n = 128
    s_max = n * 2**23
    v_max = n * n * 2**46
    d_max = (n - 1) * 2**46
    selector_cross = v_max * v_max * (s_max * s_max + 1) * (v_max + n * d_max + 1)
    assert s_max < 2**31
    assert v_max < 2**61
    assert selector_cross < 2**248 < FR
    lomb_cross = n**10 * 2**172
    assert lomb_cross < 2**246 < FR


def test_real_inputs_share_pool_scale_window_and_source(prepared):
    work, report = prepared
    assert report["realOnly"] is True
    valid = [d for d in report["datasets"] if "excluded" not in d]
    assert valid
    for dataset in valid:
        endpoints = []
        for n in COUNTS:
            data = read(work / "inputs" / f"{dataset['name']}-n{n}.json")
            assert len(data["csiI"]) == len(data["csiQ"]) == n
            assert all(len(row) == 4004 for row in data["csiI"] + data["csiQ"])
            assert data["candidateCount"] == dataset["candidateCount"]
            times = data["timestampsMs"]
            assert len(times) == len(set(times)) == n
            assert all(a < b for a, b in zip(times, times[1:]))
            endpoints.append((times[0], times[-1]))
            assert dataset["variants"][str(n)]["sourceRows"][0] == dataset["variants"]["64"]["sourceRows"][0]
        assert len(set(endpoints)) == 1


def test_completed_real_witnesses_match_python(prepared):
    work, _ = prepared
    completed = [work / f"n{n}/evaluation.json" for n in COUNTS]
    if not all(path.exists() for path in completed):
        pytest.skip("Run all real circuit witnesses before the final integration check")
    for path in completed:
        report = read(path)
        assert len(report["results"]) == 5
        assert all(result["integerReferenceMatches"] for result in report["results"])
