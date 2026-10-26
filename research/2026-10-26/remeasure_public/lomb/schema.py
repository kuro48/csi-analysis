"""Schema, direct proof-public decoding, and integer validation for every compared circuit."""

import math
import numpy as np
from reference import basis, estimate_integer

FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617
NORMAL = ["csiCommitment", "isNormal", "selectedSubcarrier", "estimatedFrequencyBin", "globalPeakFrequencyBin"]


def fields(c):
    specs = [(n, [], False) for n in NORMAL] + [
        ("debugSignedI", [64, c], True),
        ("debugSignedQ", [64, c], True),
        ("debugMagnitudeSquared", [64, c], False),
        ("debugCentered", [64, c], True),
        ("debugSignalNorm", [c], False),
        ("debugCosBasis", [32, 64], True),
        ("debugSinBasis", [32, 64], True),
        ("debugCosNorm", [32], False),
        ("debugSinNorm", [32], False),
        ("debugCrossNorm", [32], True),
        ("debugDeterminant", [32], False),
        ("debugCosProjection", [c, 32], True),
        ("debugSinProjection", [c, 32], True),
        ("debugNumerator", [c, 32], False),
        ("debugDenominator", [c, 32], False),
        ("debugBandPeak", [c], False),
        ("debugGlobalPeak", [c], False),
        ("timestampsMs", [64], False),
    ]
    result = []
    offset = 0
    for name, shape, signed in specs:
        n = math.prod(shape)
        result.append(
            {
                "name": name,
                "shape": shape,
                "signed": signed,
                "count": n,
                "public_start_zero_based": offset,
                "role": "public_input" if name == "timestampsMs" else "public_output",
            }
        )
        offset += n
    return result


BINDINGS = """
    // Every stage below is part of THIS comparison proof's public statement.
    for (var i = 0; i < SAMPLE_COUNT; i++) {
        for (var sc = 0; sc < SUBCARRIERS; sc++) {
            debugSignedI[i][sc] <== signedI[i][sc];
            debugSignedQ[i][sc] <== signedQ[i][sc];
            debugMagnitudeSquared[i][sc] <== magnitudeSquared[i][sc];
            debugCentered[i][sc] <== centered[i][sc];
        }
    }
    for (var f = 0; f < FREQS; f++) {
        debugCosNorm[f] <== cosNorm[f];
        debugSinNorm[f] <== sinNorm[f];
        debugCrossNorm[f] <== basisCrossNorm[f];
        debugDeterminant[f] <== determinantBasis[f];
        for (var i = 0; i < SAMPLE_COUNT; i++) {
            debugCosBasis[f][i] <== timestampBasis.cosBasis[f][i] - TRIG_OFFSET;
            debugSinBasis[f][i] <== timestampBasis.sinBasis[f][i] - TRIG_OFFSET;
        }
    }
    for (var sc = 0; sc < SUBCARRIERS; sc++) {
        debugSignalNorm[sc] <== signalNorm[sc];
        debugBandPeak[sc] <== targetMaxIndex[sc][NORMAL_BINS-1];
        debugGlobalPeak[sc] <== globalMaxIndex[sc][FREQS-1];
        for (var f = 0; f < FREQS; f++) {
            debugCosProjection[sc][f] <== cosineProjection[sc][f];
            debugSinProjection[sc][f] <== sineProjection[sc][f];
            debugNumerator[sc][f] <== scoreNumerator[sc][f];
            debugDenominator[sc][f] <== scoreDenominator[sc][f];
        }
    }
"""


def source(original, c):
    marker = "    64,\n    8,\n    32,"
    assert original.count(marker) == 1
    text = original.replace("LombScargleCSIEndToEnd", "LombScarglePublicComparison").replace(
        marker, f"    64,\n    {c},\n    32,"
    )
    declarations = "\n    // Intentionally public intermediate values for the compared proof.\n"
    for field in fields(c)[5:-1]:
        declarations += f"    signal output {field['name']}{''.join('['+str(n)+']' for n in field['shape'])};\n"
    needle = "    signal output globalPeakFrequencyBin;"
    assert text.count(needle) == 1
    text = text.replace(needle, needle + declarations)
    marker = "\n}\n\n// Feasibility-sized"
    assert text.count(marker) == 1
    return "// PUBLIC-INTERMEDIATE COMPARISON: CSI/stages intentionally revealed.\n" + text.replace(
        marker, BINDINGS + marker
    )


def names(name, shape):
    if not shape:
        return [name]
    return [x for i in range(shape[0]) for x in names(f"{name}[{i}]", shape[1:])]


def reshape(values, shape):
    if not shape:
        return values[0]
    if len(shape) == 1:
        return values
    stride = math.prod(shape[1:])
    return [reshape(values[i * stride : (i + 1) * stride], shape[1:]) for i in range(shape[0])]


def decode(public, schema):
    assert len(public) == schema["n_public_total"]
    assert all(isinstance(x, str) and 0 <= int(x) < FIELD for x in public)
    result = {}
    for f in schema["fields"]:
        values = []
        for x in public[f["public_start_zero_based"] : f["public_start_zero_based"] + f["count"]]:
            n = int(x)
            values.append(str(n - FIELD if f["signed"] and n > FIELD // 2 else n))
        result[f["name"]] = reshape(values, f["shape"])
    return result


def validate(d, inp, old):
    ref = estimate_integer(inp)
    for name in NORMAL[1:]:
        assert int(d[name]) == ref[name] == int(old[name]), name
    assert [int(x) for x in d["timestampsMs"]] == inp["timestampsMs"]
    si = np.asarray(inp["csiI"], dtype=object) - 2048
    sq = np.asarray(inp["csiQ"], dtype=object) - 2048
    mag = si * si + sq * sq
    y = 64 * mag - mag.sum(axis=0)
    c, s = basis(inp["timestampsMs"])
    cc = (c * c).sum(axis=1)
    ss = (s * s).sum(axis=1)
    cs = (c * s).sum(axis=1)
    det = cc * ss - cs * cs
    cp = c @ y
    sp = s @ y
    yy = (y * y).sum(axis=0)
    expected = {
        "debugSignedI": si,
        "debugSignedQ": sq,
        "debugMagnitudeSquared": mag,
        "debugCentered": y,
        "debugSignalNorm": yy,
        "debugCosBasis": c,
        "debugSinBasis": s,
        "debugCosNorm": cc,
        "debugSinNorm": ss,
        "debugCrossNorm": cs,
        "debugDeterminant": det,
        "debugCosProjection": cp.T,
        "debugSinProjection": sp.T,
        "debugNumerator": (ss[:, None] * cp * cp - 2 * cs[:, None] * cp * sp + cc[:, None] * sp * sp).T,
        "debugDenominator": (det[:, None] * yy[None, :]).T,
    }
    for name, value in expected.items():
        assert np.array_equal(np.asarray(d[name], dtype=object).astype(object), value.astype(str).astype(object)), name
    for sc in range(si.shape[1]):
        one = {**inp, "csiI": [[x[sc]] for x in inp["csiI"]], "csiQ": [[x[sc]] for x in inp["csiQ"]]}
        one_ref = estimate_integer(one, (c, s))
        assert int(d["debugBandPeak"][sc]) == one_ref["estimatedFrequencyBin"]
        assert int(d["debugGlobalPeak"][sc]) == one_ref["globalPeakFrequencyBin"]
    return {
        "normal_outputs_match_old_accuracy": True,
        "normal_outputs_match_integer_reference": True,
        "all_intermediate_values_checked": True,
    }


def trace(d, mapping):
    selected = int(d["selectedSubcarrier"])
    band = int(d["estimatedFrequencyBin"])
    wave = [
        {
            "sample": i,
            "time_ms": d["timestampsMs"][i],
            "signed_i": d["debugSignedI"][i][selected],
            "signed_q": d["debugSignedQ"][i][selected],
            "magnitude_squared": d["debugMagnitudeSquared"][i][selected],
            "centered_x64": d["debugCentered"][i][selected],
            "centered_display": int(d["debugCentered"][i][selected]) / 64,
            "cos_basis_at_peak": d["debugCosBasis"][band][i],
            "sin_basis_at_peak": d["debugSinBasis"][band][i],
        }
        for i in range(64)
    ]
    spectra = [
        {
            "local_sc": sc,
            "physical_tone": mapping[sc],
            "bin": f,
            "bpm": (127 + 29 * f) / 2540 * 60,
            "numerator": d["debugNumerator"][sc][f],
            "denominator": d["debugDenominator"][sc][f],
            "score_display": int(d["debugNumerator"][sc][f]) / int(d["debugDenominator"][sc][f]),
            "selected": sc == selected,
        }
        for sc in range(len(mapping))
        for f in range(32)
    ]
    return {
        "selected_local_sc": selected,
        "selected_physical_tone": mapping[selected],
        "physical_tone_mapping": mapping,
        "waveform": wave,
        "spectra": spectra,
        "normal_outputs": {k: d[k] for k in NORMAL},
        "display_note": "Only divide public centered by64 and public numerator/denominator for display. No Python waveform/spectrum replacement.",
    }
