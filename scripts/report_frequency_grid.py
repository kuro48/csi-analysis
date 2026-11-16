"""Publish completed actual nine-condition real CSI comparisons, never projected timings."""
import argparse
import re
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate_frequency_grid import COUNTS, GRIDS, REPRESENTATIVE, ROOT, pin, read, save
from evaluate_subcarrier_selection import sha256
from frequency_grid_reference import frequencies
from report_sample_counts import circuit_shape


def peak_alignment_diagnostic(work, datasets, records, output):
    """Explain a measured peak switch using only the same real selected waveform."""
    name, n = "csi_sample_main2", 96
    dataset = next(row for row in datasets["datasets"] if row["name"] == name)
    source = work / "inputs" / f"{name}-n{n}.json"
    assert sha256(source) == dataset["variants"]["n96k64"]["inputSha256"]
    data = read(source)
    column = next(e for e in records["n96k64"]["evaluation"]["results"] if e["name"] == name)["circuit"][
        "selectedSubcarrier"
    ]
    i = np.asarray(data["csiI"], dtype=float)[:, column] - 2048
    q = np.asarray(data["csiQ"], dtype=float)[:, column] - 2048
    y = i * i + q * q
    y -= y.mean()
    times = np.asarray(data["timestampsMs"]) / 1000
    result = {"capture": name, "sampleCount": n, "selectedSubcarrier": column, "topFits": {}}
    curves = {}
    for k in (64, 128, 2048):
        freq = frequencies(k) if k != 2048 else np.asarray(datasets["denseReferenceHz"])
        c = np.cos(2 * np.pi * freq[:, None] * times)
        s = np.sin(2 * np.pi * freq[:, None] * times)
        cc, ss, cs = (c * c).sum(1), (s * s).sum(1), (c * s).sum(1)
        cp, sp = (c * y).sum(1), (s * y).sum(1)
        fit = (ss * cp * cp - 2 * cs * cp * sp + cc * sp * sp) / ((cc * ss - cs * cs) * (y * y).sum())
        curves[k] = (freq * 60, fit)
        if k != 2048:
            actual = next(e for e in records[f"n96k{k}"]["evaluation"]["results"] if e["name"] == name)["circuit"]
            assert abs(actual["global_bpm"] - freq[int(np.argmax(fit))] * 60) < 1e-10
        indices = np.argsort(fit)[-4:][::-1]
        result["topFits"][str(k)] = [
            {"cyclesPerMinute": float(freq[j] * 60), "normalizedFit": float(fit[j])} for j in indices
        ]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    for ax, limits, title in zip(axes, ((2.9, 14), (12.7, 13.5)), ("Competing peaks", "Grid positions near the peak")):
        ax.plot(*curves[2048], color="black", linewidth=1, label="Python K=2048")
        ax.scatter(*curves[64], marker="o", s=36, label="Python K=64", zorder=3)
        ax.scatter(*curves[128], marker="x", s=36, label="Python K=128", zorder=3)
        ax.axhline(curves[2048][1][0], color="gray", linestyle=":", label="Fit at 3 cycles/min")
        ax.set(xlim=limits, xlabel="Frequency (cycles/min)", ylabel="Normalized LS fit", title=title)
        if limits[0] > 10:
            ax.set_ylim(0.075, 0.09)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.2)
    fig.suptitle("Real csi_sample_main2, N=96, same selected subcarrier")
    fig.savefig(output / "peak-alignment.png", dpi=180)
    plt.close(fig)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT / ".local/frequency-grid")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/progress/2026-11-16-frequency-grid")
    args = parser.parse_args()
    work = args.work.resolve()
    out = args.output.resolve()
    pin(work)
    formatting = read(work / "source-formatting.json") if (work / "source-formatting.json").exists() else None
    if formatting:
        import hashlib

        for change in formatting["changes"]:
            source = (ROOT / change["file"]).read_bytes()
            assert hashlib.sha256(source).hexdigest() == change["repositorySha256"]
            assert (
                hashlib.sha256(source + b"\n" * change["removedTrailingNewlines"]).hexdigest()
                == change["measuredSha256"]
            )
    environment = read(work / "environment.json")
    for name, expected in environment.get("sharedHelperSha256", {}).items():
        assert sha256(ROOT / name) == expected, name
    datasets = read(work / "datasets.json")
    previous = Path(datasets["previousWork"])
    assert datasets["realOnly"]
    assert sha256(previous / "datasets.json") == datasets["previousDatasetSha256"]
    assert sha256(previous / "spectral-reference.json") == datasets["previousSpectralSha256"]
    previous_spectral = read(previous / "spectral-reference.json")
    rows = [row for row in datasets["datasets"] if "excluded" not in row]
    assert len(rows) == 5
    records = {}
    summary = []
    same_grid_mismatches = []
    out.mkdir(parents=True, exist_ok=True)
    evidence = out / "evidence"
    evidence.mkdir(exist_ok=True)
    for n in COUNTS:
        for k in GRIDS:
            profile = f"n{n}k{k}"
            target = work / profile
            evaluation = read(target / "evaluation.json")
            entries = evaluation["results"]
            assert len(entries) == 5
            measured = previous / f"n{n}" if k == 32 else target
            proof = read(measured / REPRESENTATIVE / "prove-metrics.json")
            ledger = read(measured / "ledger-measurements.json")
            assert ledger["negativeControl"]["modifiedIsNormalRejected"] is True
            manifest = (
                read(ROOT / ".local/circom-adaptive-4004/artifacts.json")
                if (n, k) == (64, 32)
                else read(measured / "artifacts.json")
            )
            assert sha256(measured / REPRESENTATIVE / "bundle.json") == ledger["recordedProofSha256"]
            assert sha256(manifest["files"]["verificationKey"]) == manifest["sha256"]["verificationKey"]
            shape = circuit_shape(manifest["files"]["r1cs"])
            assert shape["publicSignalCount"] == n + 6
            assert read(Path(manifest["files"]["verificationKey"]))["nPublic"] == n + 6
            metric = {
                "sampleCount": n,
                "frequencyGridCount": k,
                "timingsReusedFromPreviousExperiment": k == 32,
                "constraints": shape["constraints"],
                "publicSignalCount": n + 6,
                "proveSeconds": proof["proveSeconds"],
                "evmRecordMs": ledger["evm"]["recordCommitMs"],
                "fabricRecordMs": ledger["fabric"]["recordCommitMs"],
                "evmVerifyMedianMs": ledger["evm"]["warmSummary"]["medianMs"],
                "fabricVerifyMedianMs": ledger["fabric"]["warmSummary"]["medianMs"],
                "evmRecordGas": int(ledger["evm"]["gasUsed"]),
            }
            for label in ("sameGrid", "samePointsDense", "fullSameColumnDense", "fullDense", "previousSpectral"):
                differences = [entry["differences"][label] for entry in entries]
                metric[label] = {
                    "meanAbsoluteDifferenceBpm": float(
                        np.mean([d["globalBpmAbsoluteDifference"] for d in differences])
                    ),
                    "maxAbsoluteDifferenceBpm": max(d["globalBpmAbsoluteDifference"] for d in differences),
                    "isNormalMatches": sum(d["isNormalMatches"] for d in differences),
                    "selectionMatches": sum(d["selectionMatches"] for d in differences),
                }
            for entry in entries:
                assert entry["integerReferenceMatches"]
                assert sha256(target / entry["name"] / "public.json") == entry["publicSha256"]
                original = read(previous / f"n{n}" / entry["name"] / "public.json")["publicSignals"]
                actual = read(target / entry["name"] / "public.json")["publicSignals"]
                assert actual[0] == original[0] and actual[2] == original[2] and actual[5:] == original[5:]
                d = entry["differences"]["sameGrid"]
                if (
                    d["globalBpmAbsoluteDifference"] > 0
                    or d["normalBandBpmAbsoluteDifference"] > 0
                    or not d["isNormalMatches"]
                ):
                    same_grid_mismatches.append({"profile": profile, "capture": entry["name"], **d})
            summary.append(metric)
            records[profile] = {"evaluation": evaluation, "proving": proof, "ledgers": ledger, "circuitShape": shape}
            for source, destination in [
                (measured / REPRESENTATIVE / "bundle.json", f"{profile}-proof.json"),
                (Path(manifest["files"]["verificationKey"]), f"{profile}-verification-key.json"),
                (measured / "evm.json", f"{profile}-evm-deployment.json"),
                (measured / "fabric/deployment/manifest.json", f"{profile}-fabric-deployment.json"),
            ]:
                shutil.copyfile(source, evidence / destination)
            save(evidence / f"{profile}-artifact-hashes.json", manifest["sha256"])
            if k != 32:
                for label, path in [
                    ("compile", target / "compile.log"),
                    ("setup", target / "setup.log"),
                    ("prove", target / REPRESENTATIVE / "prove.log"),
                    ("fabric-deploy", target / "fabric/deploy.log"),
                    ("fabric-resume", target / "fabric/resume.log"),
                ]:
                    if path.exists():
                        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", path.read_text())
                        (evidence / f"{profile}-{label}.txt").write_text(
                            "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
                        )
    alignment = peak_alignment_diagnostic(work, datasets, records, out)
    convergence = [
        {
            "name": r["name"],
            "differenceBpm": abs(r["fullDensePython"]["global_bpm"] - r["full4096Python"]["global_bpm"]),
        }
        for r in rows
    ]
    save(
        out / "results.json",
        {
            "realOnly": True,
            "referenceMeaning": "Python agreement, not ground-truth breathing accuracy",
            "sourceSha256": read(work / "measured-source-hashes.json")
            if (work / "measured-source-hashes.json").exists()
            else read(work / "source-hashes.json"),
            "repositorySourceSha256": read(work / "source-hashes.json"),
            "sourceFormattingAfterMeasurement": formatting,
            "datasets": datasets,
            "previousSpectralDefinition": {
                key: previous_spectral[key] for key in ("method", "frequencyGridHz", "bandHz", "fullTimestampPolicy")
            },
            "environment": environment,
            "summary": summary,
            "measurements": records,
            "referenceConvergence2048To4096": convergence,
            "realPeakAlignmentDiagnostic": alignment,
            "sameGridFloatMismatches": same_grid_mismatches,
        },
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    for ax, label, title in zip(
        axes, ("fullDense", "samePointsDense"), ("All-point Python reference", "Same-sample Python reference")
    ):
        values = np.array(
            [
                [
                    next(m for m in summary if m["sampleCount"] == n and m["frequencyGridCount"] == k)[label][
                        "meanAbsoluteDifferenceBpm"
                    ]
                    for k in GRIDS
                ]
                for n in COUNTS
            ]
        )
        im = ax.imshow(values, cmap="YlOrRd", vmin=0)
        for i in range(3):
            for j in range(3):
                ax.text(
                    j,
                    i,
                    f"{values[i,j]:.4f}",
                    ha="center",
                    va="center",
                    color="black",
                    bbox=dict(facecolor="white", alpha=0.65, edgecolor="none"),
                )
        ax.set(
            xticks=range(3),
            xticklabels=GRIDS,
            yticks=range(3),
            yticklabels=COUNTS,
            xlabel="Frequency grid count",
            ylabel="Time sample count",
            title=title,
        )
        fig.colorbar(im, ax=ax, label="Mean absolute difference (cycles/min)")
    fig.savefig(out / "frequency-difference.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    for ax, key, title in zip(
        axes,
        ("proveSeconds", "evmVerifyMedianMs", "fabricVerifyMedianMs"),
        ("Proof processing (seconds)", "Local EVM verification (ms)", "Local Fabric verification (ms)"),
    ):
        for n in COUNTS:
            ax.plot(
                GRIDS,
                [
                    next(m for m in summary if m["sampleCount"] == n and m["frequencyGridCount"] == k)[key]
                    for k in GRIDS
                ],
                "o-",
                label=f"N={n}",
            )
        ax.set(xticks=GRIDS, xlabel="Frequency grid count", title=title)
        ax.legend()
        ax.grid(alpha=0.25)
    fig.savefig(out / "timings.png", dpi=180)
    plt.close(fig)
    lines = [
        "# 実測CSI：時刻点数 × 周波数グリッド数の比較",
        "",
        "実測CSI 5件、時刻点数64・96・128 × 周波数グリッド数32・64・128の9条件。合成CSIは使用していない。",
        "32グリッドの回路出力と台帳計測は前回の実測を再利用し、参照との差を今回の固定参照で再計算した。追加6条件は実際にコンパイル・証明生成・台帳記録・検証した。",
        "",
        "## 固定した条件",
        "",
        "- 前回と同じ入力JSON（全候補I/Q、時刻、量子化、nonce）。各N内ではKが変わっても入力・選択列・CSIコミットメントは同一。",
        "- 周波数範囲：127/2540〜1026/2540 Hz（3〜24.2362周期/分）。正常帯域：0.1〜22/60 Hz（6〜22周期/分）。",
        "- 回路周波数：f(j)=127/2540 + j × 899/[2540(K−1)]、j=0..K−1。K=32・64・128で刻みは約0.6850・0.3371・0.1672周期/分。",
        "- 正常帯域binはK=32:5〜27、K=64:9〜56、K=128:18〜113。探索範囲や物理的判定帯域を増点に伴って広げない。",
        "- 同式Python参照は2,048周波数に固定。元の全時刻点＋同じ選択式で選ぶ列を主参照とする。時刻は前回同様にミリ秒へ丸める。",
        "- 「同時刻点」参照は回路と同じ時刻点・選択列・量子化CSIを使い、周波数だけを2,048点にする。グリッド近似の影響を分けるための比較。",
        "- 正解呼吸数のラベルはない。以下はPythonとの差・一致であり、実際の呼吸判定の正解率ではない。",
        "",
        "## Pythonとの差（全域ピーク、周期/分）",
        "",
        "| 時刻点数 | グリッド数 | 全時刻点Pythonとの差の平均 | 同時刻点Pythonとの差の平均 | 全時刻点PythonとのisNormal一致 | 前回の独立Python選択法との差 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for m in summary:
        lines.append(
            f"| {m['sampleCount']} | {m['frequencyGridCount']} | {m['fullDense']['meanAbsoluteDifferenceBpm']:.4f} | {m['samePointsDense']['meanAbsoluteDifferenceBpm']:.4f} | {m['fullDense']['isNormalMatches']}/5 | {m['previousSpectral']['meanAbsoluteDifferenceBpm']:.4f} |"
        )
    best = min(summary, key=lambda m: m["fullDense"]["meanAbsoluteDifferenceBpm"])
    lines += [
        "",
        f"今回の5件で全時刻点参照との差が最小だった条件はN={best['sampleCount']}、K={best['frequencyGridCount']}。他の収集条件での最適値を保証するものではない。",
        "前回の独立Python選択法はfloating-mean LS・355周波数・別のサブキャリア選択式で、旧帯域内の候補は約6.4794〜21.4767周期/分。主参照の6〜22周期/分とは帯域定義も異なるため、今回の同式参照とは分けて解釈する。",
        "**前回の表とは参照グリッドが異なるため、32グリッド行の差も数値が変わる。今回の9条件同士を比較する。**",
        "",
        f"参照を2,048から4,096周波数に増やした場合、5件のピーク差の最大は{max(r['differenceBpm'] for r in convergence):.6f}周期/分。これは参照グリッドに対する感度確認であり、正解値の保証ではない。",
        "",
        "## 同入力・同グリッドの整数／実数Pythonとの一致",
        "",
        "全45条件の回路出力（選択列・全域ピーク・帯域内ピーク・isNormal）は整数Python参照と一致した。実数Pythonとは、丸めにより次の差が残った。",
        "",
        "| N / K | CSI | 全域ピーク差 | 帯域内ピーク差 | isNormal一致 |",
        "|---|---|---:|---:|---|",
    ]
    for item in same_grid_mismatches:
        lines.append(
            f"| {item['profile']} | {item['capture']} | {item['globalBpmAbsoluteDifference']:.4f} | {item['normalBandBpmAbsoluteDifference']:.4f} | {item['isNormalMatches']} |"
        )
    lines += [
        "",
        "## 実際の証明・記録・検証時間",
        "",
        "| N | K | 制約数 | 証明処理 秒 | EVM記録 ms | EVM検証 ms | Fabric記録 ms | Fabric検証 ms | EVM記録gas |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in summary:
        lines.append(
            f"| {m['sampleCount']} | {m['frequencyGridCount']} | {m['constraints']:,} | {m['proveSeconds']:.2f} | {m['evmRecordMs']:.2f} | {m['evmVerifyMedianMs']:.2f} | {m['fabricRecordMs']:.2f} | {m['fabricVerifyMedianMs']:.2f} | {m['evmRecordGas']:,} |"
        )
    lines += [
        "",
        "初回検証時間（未起動状態からのコールドスタートを保証する値ではない）：",
        "",
        "| N | K | EVM初回 ms | Fabric初回 ms |",
        "|---|---|---:|---:|",
    ]
    for n in COUNTS:
        for k in GRIDS:
            ledger = records[f"n{n}k{k}"]["ledgers"]
            lines.append(
                f"| {n} | {k} | {ledger['evm']['firstVerifyMs']:.2f} | {ledger['fabric']['firstVerifyMs']:.2f} |"
            )
    lines += [
        "",
        "- 代表実測CSI csi_20260519_114943の全4,004候補を使用。各条件につき証明生成・記録1回、検証は初回＋追加10回。表は追加10回の中央値。",
        "- 証明処理は鍵・R1CS・witness読み込み、群検査、全制約検査、Groth16生成、native検証を含む。witness作成、setup、デプロイは別。",
        "- EVMはローカルGanache chain1337、Fabricはローカル2組織ネットワーク。Sepoliaの測定ではない。",
        "- 検証はEVM eth_call / Fabric evaluateTransactionによる台帳側検証付き照会。新たな検証トランザクションの確定時間ではない。",
        "- FabricのBatchTimeoutは2秒。記録待ち時間はこの設定の影響を受ける。",
        "- K=32の時間は前回実験の値。追加条件の実行順はN64/K64→N64/K128→N96/K64→N96/K128→N128/K64→N128/K128。反復・ランダム順序による統計的な速度比較ではない。",
        "- ホストはIntel i5-8500B、メモリ16GiB。swapとOSキャッシュ・他サービスの影響を受ける。小さな時間差をグリッド数だけの効果と解釈しない。",
        "- Kを増やしても公開信号数はN+6のまま。新しい回路・鍵・検証器を個別配備し、実際の記録・検証と改変isNormalの拒否を全条件で確認。",
        "- 記録gasには出力値が0か非0かによるストレージ費用の違いも含まれる。Kによる制約数増加が、そのまま台帳のgas増加になるわけではない。",
        "- テスト用単独セットアップ。実運用のtrusted setupやインフラ費用の評価は含まない。",
        "",
        "## 各実測CSIの出力",
        "",
        "| CSI | N | K | 選択列 | 全域ピーク 周期/分 | 全点参照 周期/分 | 差 | isNormal |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        for n in COUNTS:
            for k in GRIDS:
                entry = next(e for e in records[f"n{n}k{k}"]["evaluation"]["results"] if e["name"] == row["name"])
                c = entry["circuit"]
                lines.append(
                    f"| {row['name']} | {n} | {k} | {c['selectedSubcarrier']} | {c['global_bpm']:.4f} | {row['fullDensePython']['global_bpm']:.4f} | {entry['differences']['fullDense']['globalBpmAbsoluteDifference']:.4f} | {c['isNormal']} |"
                )
    lines += [
        "",
        "## グリッドを増やしても差が増える例",
        "",
        "実測csi_sample_main2、N=96では、同じ選択列・時刻点でグリッド上のピーク順位が変わった。以下は実数Pythonの適合度で、呼吸の正解確率ではない。",
        "",
        "| グリッド数 | 最大適合の周波数 周期/分 | 適合度 | 2位の周波数 周期/分 | 適合度 |",
        "|---|---:|---:|---:|---:|",
        *[
            f"| {k} | {alignment['topFits'][str(k)][0]['cyclesPerMinute']:.6f} | {alignment['topFits'][str(k)][0]['normalizedFit']:.8f} | {alignment['topFits'][str(k)][1]['cyclesPerMinute']:.6f} | {alignment['topFits'][str(k)][1]['normalizedFit']:.8f} |"
            for k in (64, 128, 2048)
        ],
        "",
        "64グリッドには約13.1125周期/分の候補があるが、128グリッドの近隣候補は約13.0329と13.2001周期/分。2,048点参照の約13.1046周期/分に対して64点側の候補が近く、僅差のピーク順位が入れ替わる。グリッドは入れ子ではないため、点数だけでは差の単調減少を保証できない。",
        "",
        "除外は前回と同じ2ファイル（候補数8,100で容量超過、破損フレーム）。入力列の切り捨てや合成データによる補完はしていない。",
        "",
        "生の測定値・取引ID・全検証反復値：[results.json](results.json)。公開証明・鍵・配備情報・ログ：[evidence](evidence/)。",
        "実装・再実行手順：[周波数グリッド比較手順](../../frequency-grid-comparison.md)。",
        "計測後の整形は新規回路2ファイルの末尾空行削除のみ。計測時と保存時のソースハッシュ、元バイト列を復元できる差分をresults.jsonに残した。回路・鍵・証明・数値は変更していない。",
        "",
        "![周波数差](frequency-difference.png)",
        "",
        "![処理時間](timings.png)",
        "",
        "![実測CSIのピークとグリッド位置](peak-alignment.png)",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines))
    print({"bestByFullDenseDifference": best, "floatMismatchCount": len(same_grid_mismatches)})


if __name__ == "__main__":
    main()
