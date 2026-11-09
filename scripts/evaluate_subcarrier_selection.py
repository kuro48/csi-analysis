"""Offline evaluation; never selects inputs for the production proving pipeline.

Compare exact integer parity, quantization, subsampling, and an explicitly
different floating-mean Lomb-Scargle reference. Python is not ground truth.
"""

import argparse
import hashlib
import html
import json
import platform
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.adaptive_csi_input import canonicalize_all_columns  # noqa: E402

GRID = np.linspace(0.05, (127 + 29 * 31) / 2540, 355)
BAND = (GRID >= (127 + 29 * 5) / 2540) & (GRID <= (127 + 29 * 27) / 2540)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def exact_scores(data):
    """Python arbitrary precision, with exact rational ordering and first-index ties."""
    n = len(data["csiI"])
    scores = []
    for column in range(data["candidateCount"]):
        power = [
            (int(i[column]) - 2048) ** 2 + (int(q[column]) - 2048) ** 2 for i, q in zip(data["csiI"], data["csiQ"])
        ]
        s = sum(power)
        v = n * sum(p * p for p in power) - s * s
        d = sum((b - a) ** 2 for a, b in zip(power, power[1:]))
        eligible = s >= n * 16 and 0 < v <= s * s
        scores.append(Fraction(v * v if eligible else 0, (s * s + 1) * (v + n * d + 1)))
    return scores


def float_scores(matrix):
    power = np.abs(matrix) ** 2
    n = len(power)
    s = power.sum(axis=0)
    # Stable equivalent of N sum(P²) - sum(P)²; avoid cancellation near constants.
    v = n * np.sum((power - power.mean(axis=0)) ** 2, axis=0)
    d = np.sum(np.diff(power, axis=0) ** 2, axis=0)
    eligible = (s >= n * 16) & (v > 0) & (v <= s * s) & (np.ptp(power, axis=0) > 0)
    return np.where(eligible, v * v / ((s * s + 1) * (v + n * d + 1)), 0)


def winner(scores):
    index = max(range(len(scores)), key=lambda i: scores[i])
    return index if scores[index] > 0 else None


def rank(scores, index):
    """Ordinal rank, preserving the circuit's lower-index tie break."""
    if index is None or scores[index] <= 0:
        return None
    return 1 + int(sum(s > scores[index] or (s == scores[index] and i < index) for i, s in enumerate(scores)))


def periodograms(times, matrix, frequencies=GRID):
    """Batched floating-mean LS, normalized explained variance of power |CSI|².

    Fits a*cos(w*t)+b*sin(w*t)+c separately at each frequency. Tested against
    scipy.signal.lombscargle(..., floating_mean=True, normalize=True).
    The grid is dense for interpolation, not an increase in physical resolution.
    """
    y = np.abs(matrix) ** 2
    y -= y.mean(axis=0)
    energy = np.sum(y * y, axis=0)
    result = np.zeros((len(frequencies), matrix.shape[1]))
    for i, frequency in enumerate(frequencies):
        phase = 2 * np.pi * frequency * times
        basis = np.column_stack((np.cos(phase), np.sin(phase)))
        basis -= basis.mean(axis=0)
        projection = basis.T @ y
        fitted_energy = np.sum(projection * (np.linalg.pinv(basis.T @ basis) @ projection), axis=0)
        np.divide(fitted_energy, energy, out=result[i], where=energy > 0)
    return np.clip(result, 0, 1)


def spectral_scores(spectra, eligible):
    return np.where(eligible, spectra[BAND].max(axis=0), 0)


def power_diagnostics(matrix, index):
    power = np.abs(matrix[:, index]) ** 2
    mean = float(power.mean())
    cv_squared = float(power.var() / (mean * mean)) if mean else None
    return {
        "meanPower": mean,
        "powerCvSquared": cv_squared,
        "eligible": bool(mean >= 16 and cv_squared is not None and 0 < cv_squared <= 1 and np.ptp(power) > 0),
    }


def unique_rows(timestamps):
    order = np.argsort(timestamps, kind="stable")
    ms = np.rint((timestamps[order] - timestamps[order[0]]).astype(float) / 1e6).astype(np.int64)
    return order[np.concatenate(([True], np.diff(ms) > 0))]


def run_circuit(data, wasm):
    with tempfile.TemporaryDirectory(prefix="csi-selection-") as folder:
        source, output = Path(folder) / "input.json", Path(folder) / "public.json"
        source.write_text(json.dumps(data))
        started = time.perf_counter()
        subprocess.run(
            ["node", str(ROOT / "scripts/selection_witness.cjs"), str(wasm), str(source), str(output)],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        public = json.loads(output.read_text())
    if len(public) != 70 or list(map(int, public[5:69])) != data["timestampsMs"]:
        raise AssertionError("Unexpected public timestamp schema")
    if int(public[69]) != data["candidateCount"]:
        raise AssertionError("Unexpected candidate count")
    return {
        "selectedColumn": int(public[2]),
        "isNormal": int(public[1]),
        "frequencyBin": int(public[4]),
        "witnessSeconds": time.perf_counter() - started,
        "validation": "compiled WASM witness with sanity checks; no new Groth16 proof",
    }


def compare(name, matrix, timestamps, wasm, capacity, output, truth=None):
    data, metadata = canonicalize_all_columns(matrix, timestamps, capacity)
    circuit = run_circuit(data, wasm)
    exact = exact_scores(data)
    if winner(exact) != circuit["selectedColumn"]:
        raise AssertionError(f"Circuit/Python integer mismatch: {name}")
    rows = unique_rows(timestamps)
    all_matrix = matrix[rows] * metadata["sharedIqScale"]
    sampled = matrix[metadata["sourceRows"]] * metadata["sharedIqScale"]
    t_all = (timestamps[rows] - timestamps[rows[0]]).astype(float) / 1e9
    t64 = np.asarray(data["timestampsMs"]) / 1000
    quantized = (
        np.asarray(data["csiI"])[:, : matrix.shape[1]]
        - 2048
        + 1j * (np.asarray(data["csiQ"])[:, : matrix.shape[1]] - 2048)
    )
    f64, full = float_scores(sampled), float_scores(all_matrix)
    spectra, spectra64 = periodograms(t_all, all_matrix), periodograms(t64, quantized)
    spectral = spectral_scores(spectra, full > 0)
    spectral64 = spectral_scores(spectra64, np.array([x > 0 for x in exact]))
    candidates = {
        "pythonInteger64": exact,
        "pythonFloat64": f64,
        "pythonFloatAll": full,
        "pythonSpectral64": spectral64,
        "pythonSpectralAll": spectral,
    }
    selected = circuit["selectedColumn"]
    result = {
        "name": name,
        "metadata": metadata,
        "circuit": circuit,
        "pythonSelections": {key: winner(value) for key, value in candidates.items()},
        "circuitRankUnderPython": {key: rank(value, selected) for key, value in candidates.items()},
        "top10": {
            key: sorted(range(len(value)), key=lambda i: value[i], reverse=True)[:10]
            for key, value in candidates.items()
        },
        "selectedChannelMetrics": {},
        "groundTruth": truth,
        "circuitChoiceDiagnostics": {
            "float64": power_diagnostics(sampled, selected),
            "floatAll": power_diagnostics(all_matrix, selected),
        },
    }
    for label, index in {
        "circom": selected,
        "pythonSpectralAll": winner(spectral),
        "pythonFloatAll": winner(full),
    }.items():
        if index is None:
            result["selectedChannelMetrics"][label] = None
            continue
        peak = float(GRID[np.argmax(spectra[:, index])])
        result["selectedChannelMetrics"][label] = {
            "column": index,
            "fullSamplePeakHz": peak,
            "fullSamplePeakBpm": peak * 60,
            "fullSampleBandFit": float(spectra[BAND, index].max()),
            "fullSampleGlobalFit": float(spectra[:, index].max()),
            "python64PeakHz": float(GRID[np.argmax(spectra64[:, index])]),
        }
    if truth:
        result["syntheticAccuracy"] = {}
        for label, index in {"circom": selected, **result["pythonSelections"]}.items():
            peak = None if index is None else float(GRID[np.argmax(spectra[:, index])])
            result["syntheticAccuracy"][label] = {
                "correctChannel": index == truth["column"],
                "frequencyErrorBpm": None if peak is None else abs(peak - truth["frequencyHz"]) * 60,
            }
    if truth is None:
        plot_comparison(result, t_all, all_matrix, t64, quantized, spectra, output)
    return result


def plot_comparison(result, times, matrix, times64, quantized, spectra, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    selected = result["circuit"]["selectedColumn"]
    reference = result["pythonSelections"]["pythonSpectralAll"]
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), layout="constrained")
    for column, color, label in [(selected, "#12655b", "Circom"), (reference, "#bd4e32", "Python spectral")]:
        if column is None:
            continue
        power = np.abs(matrix[:, column]) ** 2
        mean, std = power.mean(), power.std()
        axes[0].plot(times, (power - mean) / max(std, 1e-12), color=color, alpha=0.7, label=f"{label}: column {column}")
        if label == "Circom":
            axes[0].scatter(
                times64,
                (np.abs(quantized[:, column]) ** 2 - mean) / max(std, 1e-12),
                color=color,
                s=12,
                label="Circuit 64 points",
            )
        axes[1].plot(GRID * 60, spectra[:, column], color=color, label=label)
    axes[0].set(xlabel="Time (s)", ylabel="Standardized CSI power", title=result["name"])
    axes[1].axvspan(GRID[BAND][0] * 60, GRID[BAND][-1] * 60, alpha=0.08, color="green")
    axes[1].set(
        xlabel="Frequency (cycles/min; not validated respiratory rate)", ylabel="Explained variance", ylim=(0, 1)
    )
    for axis in axes:
        axis.legend(loc="upper right", fontsize=8)
        axis.grid(alpha=0.2)
    fig.savefig(output / (result["name"] + ".png"), dpi=150)
    plt.close(fig)


def synthetic_cases():
    """Predeclared target column follows a known latent breathing signal.

    Includes in-band interference: spectral periodicity is not proof of breathing.
    These are controlled stress cases, not a representative clinical population.
    """
    for scenario in ["clean", "slow_drift", "in_band_interference"]:
        for seed in range(4):
            rng = np.random.default_rng(seed)
            times = np.sort(rng.uniform(0, 60, 192))
            frequency = 0.18 + 0.025 * seed
            target = 1000 + 90 * np.sin(2 * np.pi * frequency * times) + rng.normal(0, 15, len(times))
            competitor = 1000 + rng.normal(0, 60, len(times))
            if scenario == "slow_drift":
                competitor = 1000 + 350 * np.sin(2 * np.pi * 0.025 * times)
            elif scenario == "in_band_interference":
                competitor = 1000 + 300 * np.sin(2 * np.pi * 0.32 * times)
            matrix = np.column_stack(
                (target, competitor, np.full(len(times), 800), 1000 + rng.normal(0, 120, len(times)))
            ).astype(complex)
            permutation = rng.permutation(4)
            matrix = matrix[:, permutation]
            yield f"{scenario}-{seed}", matrix, np.rint(times * 1e9).astype(np.int64), {
                "column": int(np.where(permutation == 0)[0][0]),
                "frequencyHz": frequency,
                "scenario": scenario,
            }


def render_report(report, output):
    successful = [r for r in report["real"] if "circuit" in r]
    columns = ["pythonInteger64", "pythonFloat64", "pythonFloatAll", "pythonSpectral64", "pythonSpectralAll"]
    report["agreement"] = {
        key: {
            "matches": sum(r["circuit"]["selectedColumn"] == r["pythonSelections"][key] for r in successful),
            "total": len(successful),
        }
        for key in columns
    }
    rows = ""
    for result in report["real"]:
        if "error" in result:
            rows += f'<tr><td>{html.escape(result["name"])}</td><td colspan="6">Excluded: {html.escape(result["error"])}</td></tr>'
            continue
        values = [result["circuit"]["selectedColumn"], *[result["pythonSelections"][key] for key in columns]]
        rows += f'<tr><td>{html.escape(result["name"])}</td>' + "".join(f"<td>{v}</td>" for v in values) + "</tr>"
    figures = "".join(
        f'<figure><img src="{html.escape(r["name"])}.png" alt="{html.escape(r["name"])} comparison"></figure>'
        for r in successful
    )
    synthetic_rows = ""
    for scenario, counts in report["syntheticSummary"].items():
        synthetic_rows += f"<tr><td>{html.escape(scenario)}</td>"
        for key in ["circom", "pythonInteger64", "pythonSpectral64", "pythonSpectralAll"]:
            synthetic_rows += f'<td>{counts[key]["correctChannels"]} / {counts[key]["total"]}</td>'
        synthetic_rows += "</tr>"
    content = f"""<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
    <title>CSI サブキャリア選択比較</title><style>body{{font:16px/1.7 system-ui;background:#f3f6f5;color:#183a34;margin:32px auto;padding:0 24px;max-width:1200px}}h1{{font-size:32px}}table{{border-collapse:collapse;width:100%;background:white;font-size:14px}}td,th{{padding:12px;border-bottom:1px solid #ccc;text-align:left}}img{{width:100%}}figure{{margin:24px 0}}.scroll{{overflow:auto}}pre{{white-space:pre-wrap;background:#fff;padding:20px}}</style>
    <p>CSI / 評価用レポート</p><h1>Circom と Python のサブキャリア選択比較</h1>
    <p>実回路の WASM を実行。実データの正解ラベルは未提供のため、表は精度ではなく選択の一致を示します。番号は 0 始まりの CSI 列です。</p>
    <div class="scroll"><table><tr><th>CSI</th><th>Circom</th><th>Python 同式・整数64</th><th>同式・実数64</th><th>同式・実数全点</th><th>周期性・整数64</th><th>周期性・全点</th></tr>{rows}</table></div>
    <p>周期性基準: 回路の正常帯域に対応する約 0.107–0.358 Hz で、定数項付き Lomb–Scargle の説明分散率が最大の列。呼吸由来であることは保証しません。</p>
    <h2>正解が分かる合成データ：呼吸信号を含む列を選べた件数</h2>
    <div class="scroll"><table><tr><th>条件</th><th>Circom</th><th>Python 同式・整数64</th><th>周期性・整数64</th><th>周期性・全点</th></tr>{synthetic_rows}</table></div>
    <p>clean / slow_drift / in_band_interference 各4件。合成の成功率は実測の呼吸判定精度ではありません。既存の本番選択回路・WebUIは変更していません。</p>
    {figures}<p>詳細: <a href="results.json">results.json</a> / <a href="README.md">評価手順・制約</a></p></html>"""
    (output / "index.html").write_text(content)
    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=ROOT / ".local/circom-adaptive-4004/artifacts.json")
    parser.add_argument(
        "--compact-wasm",
        type=Path,
        default=ROOT / ".local/circom-adaptive/build/csi_lomb_scargle_adaptive_js/csi_lomb_scargle_adaptive.wasm",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text())
    wasm = Path(manifest["files"]["wasm"])
    if sha256(wasm) != manifest["sha256"]["wasm"] or manifest["capacity"] != 4004:
        raise ValueError("Unrecognized production WASM")
    report = {
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": platform.platform(),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        },
        "artifacts": {
            "fullWasmSha256": sha256(wasm),
            "compactWasmSha256": sha256(args.compact_wasm),
            "evaluationSha256": sha256(__file__),
            "witnessRunnerSha256": sha256(ROOT / "scripts/selection_witness.cjs"),
        },
        "frequencyGridHz": GRID.tolist(),
        "bandHz": [float(GRID[BAND][0]), float(GRID[BAND][-1])],
        "real": [],
        "synthetic": [],
        "syntheticSummary": {},
    }
    from app.services.breathing_pipeline import load_csi_matrix_with_timestamps

    for path in args.captures:
        print(f"Evaluating {path.name}", flush=True)
        source_hash = sha256(path)
        try:
            matrix, timestamps = load_csi_matrix_with_timestamps(str(path))
            result = compare(path.stem, matrix, timestamps, wasm, 4004, args.output)
            del matrix, timestamps
        except ValueError as exc:
            result = {"name": path.stem, "error": str(exc)}
        result["sourceSha256"] = source_hash
        report["real"].append(result)
        render_report(report, args.output)
        print(
            json.dumps({key: result[key] for key in ["name", "circuit", "pythonSelections", "error"] if key in result}),
            flush=True,
        )
    for name, matrix, timestamps, truth in synthetic_cases():
        result = compare(name, matrix, timestamps, args.compact_wasm, 64, args.output, truth)
        report["synthetic"].append(result)
        print(f"Synthetic {name}: {result['syntheticAccuracy']['circom']}", flush=True)
    for scenario in ["clean", "slow_drift", "in_band_interference"]:
        cases = [r for r in report["synthetic"] if r["groundTruth"]["scenario"] == scenario]
        report["syntheticSummary"][scenario] = {
            key: {
                "correctChannels": sum(r["syntheticAccuracy"][key]["correctChannel"] for r in cases),
                "total": len(cases),
            }
            for key in ["circom", "pythonInteger64", "pythonSpectral64", "pythonSpectralAll"]
        }
    render_report(report, args.output)
    print(json.dumps(report["agreement"], indent=2))


if __name__ == "__main__":
    main()
