"""Publish only completed real-data evaluation and actual ledger measurements."""
import argparse
import hashlib
import json
import re
import shutil
import struct
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
COUNTS = (64, 96, 128)


def read(path):
    return json.loads(path.read_text())


def circuit_shape(path):
    with Path(path).open("rb") as stream:
        assert stream.read(4) == b"r1cs"
        version, sections = struct.unpack("<II", stream.read(8))
        assert version == 1
        for _ in range(sections):
            kind, size = struct.unpack("<IQ", stream.read(12))
            if kind == 1:
                header = stream.read(size)
                assert len(header) == 64 and struct.unpack_from("<I", header)[0] == 32
                wires, outputs, public, private = struct.unpack_from("<IIII", header, 36)
                return {
                    "wires": wires,
                    "publicSignalCount": outputs + public,
                    "privateInputCount": private,
                    "constraints": struct.unpack_from("<I", header, 60)[0],
                }
            stream.seek(size, 1)
    raise ValueError("Missing R1CS header")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT / ".local/sample-count")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/progress/2026-11-16-sample-count")
    args = parser.parse_args()
    datasets = read(args.work / "datasets.json")
    assert datasets["realOnly"] is True
    spectral = read(args.work / "spectral-reference.json")
    assert spectral["realOnly"] is True and len(spectral["results"]) == 5
    source_hashes = read(args.work / "source-hashes.json")
    for filename, expected in source_hashes.items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == expected, filename
    records, summary, normal_band_mismatches = {}, [], []
    for n in COUNTS:
        target = args.work / f"n{n}"
        evaluation = read(target / "evaluation.json")
        proof = read(target / "csi_20260519_114943/prove-metrics.json")
        ledger = read(target / "ledger-measurements.json")
        assert ledger["negativeControl"]["modifiedIsNormalRejected"] is True
        entries = evaluation["results"]
        assert len(entries) == 5 and all(e["integerReferenceMatches"] for e in entries)
        manifest = (
            read(ROOT / ".local/circom-adaptive-4004/artifacts.json") if n == 64 else read(target / "artifacts.json")
        )
        shape = circuit_shape(manifest["files"]["r1cs"])
        assert shape["publicSignalCount"] == n + 6
        metrics = {
            "sampleCount": n,
            "captureCount": len(entries),
            "publicSignalCount": n + 6,
            "constraints": shape["constraints"],
            "representativeWitnessMs": next(e for e in entries if e["name"] == "csi_20260519_114943")["witnessMs"],
            "proveSeconds": proof["proveSeconds"],
            "evmRecordMs": ledger["evm"]["recordCommitMs"],
            "fabricRecordMs": ledger["fabric"]["recordCommitMs"],
            "evmVerifyMedianMs": ledger["evm"]["warmSummary"]["medianMs"],
            "fabricVerifyMedianMs": ledger["fabric"]["warmSummary"]["medianMs"],
            "evmRecordGas": int(ledger["evm"]["gasUsed"]),
            "localVerifyMedianMs": ledger["local"]["warmSummary"]["medianMs"],
            "fullReferenceEligibleCount": sum(e["python"]["fullReferenceRank"] is not None for e in entries),
            "meanFullReferenceScoreRatio": float(np.mean([e["python"]["fullReferenceScoreRatio"] for e in entries])),
        }
        for label in ["samePoints", "unquantizedSamePoints", "fullPoints", "fullPointsSameColumn"]:
            diffs = [e["differences"][label] for e in entries]
            ref_keys = {
                "samePoints": "floatSamePoints",
                "unquantizedSamePoints": "floatUnquantizedSamePoints",
                "fullPointsSameColumn": "floatFullSameColumn",
            }
            refs = [e["fullPython"] if label == "fullPoints" else e["python"][ref_keys[label]] for e in entries]
            band_diffs = [
                abs(e["circuit"]["estimatedFrequencyBin"] - ref["estimatedFrequencyBin"]) * 29 * 60 / 2540
                for e, ref in zip(entries, refs)
            ]
            metrics[label] = {
                "selectionMatches": sum(d["selectedColumnMatches"] for d in diffs),
                "normalityMatches": sum(d["isNormalMatches"] for d in diffs),
                "frequencyBinMatches": sum(d["globalBinMatches"] for d in diffs),
                "meanAbsoluteDifferenceBpm": float(np.mean([d["globalBpmAbsoluteDifference"] for d in diffs])),
                "maxAbsoluteDifferenceBpm": max(d["globalBpmAbsoluteDifference"] for d in diffs),
                "normalBandBinMatches": sum(value == 0 for value in band_diffs),
                "meanNormalBandAbsoluteDifferenceBpm": float(np.mean(band_diffs)),
            }
        for e in entries:
            actual, ref = e["circuit"]["estimatedFrequencyBin"], e["python"]["floatSamePoints"]["estimatedFrequencyBin"]
            if actual != ref:
                normal_band_mismatches.append(
                    {
                        "sampleCount": n,
                        "name": e["name"],
                        "circuitBin": actual,
                        "floatPythonBin": ref,
                        "absoluteDifferenceBpm": abs(actual - ref) * 29 * 60 / 2540,
                        "globalBinMatches": e["differences"]["samePoints"]["globalBinMatches"],
                        "isNormalMatches": e["differences"]["samePoints"]["isNormalMatches"],
                    }
                )
        independent_diffs = [e["variants"][str(n)]["differences"]["fullPoints"] for e in spectral["results"]]
        metrics["independentSpectralFullPoints"] = {
            "selectionMatches": sum(d["selectionMatches"] for d in independent_diffs),
            "normalityMatches": sum(d["normalityMatches"] for d in independent_diffs),
            "meanAbsoluteDifferenceBpm": float(np.mean([d["absoluteDifferenceBpm"] for d in independent_diffs])),
        }
        summary.append(metrics)
        records[str(n)] = {"evaluation": evaluation, "proving": proof, "ledgers": ledger, "circuitShape": shape}
    baseline = {
        e["name"]: e["differences"]["fullPoints"]["globalBpmAbsoluteDifference"]
        for e in records["64"]["evaluation"]["results"]
    }
    for m in summary:
        changes = [
            e["differences"]["fullPoints"]["globalBpmAbsoluteDifference"] - baseline[e["name"]]
            for e in records[str(m["sampleCount"])]["evaluation"]["results"]
        ]
        m["fullPointDifferenceChangeFrom64"] = {
            "smaller": sum(change < -1e-9 for change in changes),
            "same": sum(abs(change) <= 1e-9 for change in changes),
            "larger": sum(change > 1e-9 for change in changes),
        }
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "realOnly": True,
        "environment": read(args.work / "environment.json"),
        "sourceSha256": source_hashes,
        "datasets": datasets,
        "independentSpectralReference": spectral,
        "sameInputFloatingPointNormalBandMismatches": normal_band_mismatches,
        "summary": summary,
        "measurements": records,
        "accuracyMeaning": "agreement/difference from Python; no biological ground truth",
        "recordRepetitions": 1,
        "warmVerificationRepetitions": 10,
        "ledgerScope": "local EVM chain 1337 and local Fabric consortium; no Sepolia measurement",
    }
    (args.output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for n in COUNTS:
        target = args.work / f"n{n}"
        shutil.copyfile(target / "csi_20260519_114943/bundle.json", args.output / f"proof-n{n}.json")
        manifest = (
            read(ROOT / ".local/circom-adaptive-4004/artifacts.json") if n == 64 else read(target / "artifacts.json")
        )
        shutil.copyfile(manifest["files"]["verificationKey"], args.output / f"verification-key-n{n}.json")
        shutil.copyfile(target / "evm.json", args.output / f"evm-deployment-n{n}.json")
        shutil.copyfile(target / "fabric/deployment/manifest.json", args.output / f"fabric-deployment-n{n}.json")
        # Public artifact fingerprints let readers bind the result to its actual circuit/key.
        (args.output / f"artifact-hashes-n{n}.json").write_text(json.dumps(manifest["sha256"], indent=2) + "\n")
        logs = args.output / "logs"
        logs.mkdir(exist_ok=True)
        for name, source in [
            ("compile", target / "compile.log"),
            ("setup", target / "setup.log"),
            ("prove", target / "csi_20260519_114943/prove.log"),
            ("fabric-deploy", target / "fabric/deploy.log"),
            ("fabric-resume", target / "fabric/resume.log"),
        ]:
            if source.exists():
                content = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", source.read_text())
                (logs / f"n{n}-{name}.txt").write_text("\n".join(line.rstrip() for line in content.splitlines()) + "\n")
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    names = [e["name"] for e in records["64"]["evaluation"]["results"]]
    for name in names:
        values = [
            next(e for e in records[str(n)]["evaluation"]["results"] if e["name"] == name)["differences"]["fullPoints"][
                "globalBpmAbsoluteDifference"
            ]
            for n in COUNTS
        ]
        ax.plot(COUNTS, values, "o-", label=name, alpha=0.7)
    ax.plot(
        COUNTS,
        [m["fullPoints"]["meanAbsoluteDifferenceBpm"] for m in summary],
        "ko-",
        linewidth=3,
        label="Mean (5 captures)",
    )
    ax.set(
        xlabel="Number of time samples",
        ylabel="Absolute difference (cycles/min)",
        xticks=COUNTS,
        title="Difference from full-sample Python reference (not ground truth)",
    )
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
    fig.savefig(args.output / "python-difference.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    for label, color, rec, verify in [
        ("Local EVM", "#176f62", "evmRecordMs", "evmVerifyMedianMs"),
        ("Fabric", "#bf593a", "fabricRecordMs", "fabricVerifyMedianMs"),
    ]:
        axes[0].plot(COUNTS, [m[rec] for m in summary], "o-", color=color, label=label)
        axes[1].plot(COUNTS, [m[verify] for m in summary], "o-", color=color, label=label)
    for ax, title in zip(
        axes, ["Record through commit (one observation per N)", "Verification read (median of 10 repeats)"]
    ):
        ax.set(xlabel="Number of time samples", ylabel="Client elapsed time (ms)", xticks=COUNTS, title=title)
        ax.grid(alpha=0.2)
        ax.legend()
    fig.savefig(args.output / "ledger-timings.png", dpi=180)
    plt.close(fig)
    lines = [
        "# 実測CSI：時刻点数とPythonとの差・証明記録／検証時間",
        "",
        "合成CSIは使用していない。64・96・128点を同じ実測5ファイルで比較した。",
        "",
        "## 使用した実測データ",
        "",
        "全点数は最頻CSI幅の抽出とミリ秒時刻の重複除去を行った後の値。全点Pythonは、この全点数で計算する。",
        "",
        "| CSI | 全点数 | 候補列数 | 観測区間（秒） |",
        "|---|---:|---:|---:|",
    ]
    for d in datasets["datasets"]:
        if "excluded" not in d:
            lines.append(
                f"| {d['name']} | {d['fullPointCount']} | {d['candidateCount']} | {d['durationMs']/1000:.3f} |"
            )
    lines += [
        "",
        "## Python参照との差",
        "",
        "同じ周波数グリッド・同じ電力波形・同じ選択式で比較。BPM差は推定周期の差であり、正解呼吸数との誤差ではない。",
        "",
        "| 点数 | 同入力の整数Python一致 | 同入力の実数Python全域ピーク差の平均 | 全点Pythonとの選択一致 | 全点PythonとのisNormal一致 | 全点Pythonとの全域ピーク差の平均 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for m in summary:
        f, s = m["fullPoints"], m["samePoints"]
        lines.append(
            f"| {m['sampleCount']} | 5/5 | {s['meanAbsoluteDifferenceBpm']:.4f} | {f['selectionMatches']}/5 | {f['normalityMatches']}/5 | {f['meanAbsoluteDifferenceBpm']:.4f} |"
        )
    best = min(summary, key=lambda m: m["fullPoints"]["meanAbsoluteDifferenceBpm"])
    monotonic = all(
        right["fullPoints"]["meanAbsoluteDifferenceBpm"] <= left["fullPoints"]["meanAbsoluteDifferenceBpm"]
        for left, right in zip(summary, summary[1:])
    )
    lines += [
        "",
        f"今回の5件で全点Pythonとの平均周波数差が最小だったのは{best['sampleCount']}点。"
        + ("平均差は点数の増加に伴い減少した。" if monotonic else "平均差は点数の増加に対して単調には減少しなかった。"),
        "これはこの実測データと選択式・間引き方での結果であり、他の収集条件での最適点数を確定する結果ではない。",
    ]
    for m in summary[1:]:
        c = m["fullPointDifferenceChangeFrom64"]
        lines.append(
            f"{m['sampleCount']}点は64点に対して、全点参照との差が縮小したCSIが{c['smaller']}件、同じものが{c['same']}件、拡大したものが{c['larger']}件。"
        )
    lines += [
        "",
        "### 補助出力：正常帯域内のピーク",
        "",
        "`estimatedFrequencyBin`は正常帯域内に限定したピーク。全域ピーク`globalPeakFrequencyBin`とは別の出力である。以下は同じ入力を使う実数Pythonとの差。",
        "",
        "| 点数 | 正常帯域内ピークbin一致 | 正常帯域内ピーク差の平均（周期/分） |",
        "|---|---:|---:|",
    ]
    for m in summary:
        s = m["samePoints"]
        lines.append(
            f"| {m['sampleCount']} | {s['normalBandBinMatches']}/5 | {s['meanNormalBandAbsoluteDifferenceBpm']:.4f} |"
        )
    for mismatch in normal_band_mismatches:
        lines.append(
            f"\n{mismatch['sampleCount']}点の`{mismatch['name']}`では回路bin {mismatch['circuitBin']}、実数Python bin {mismatch['floatPythonBin']}で、差は{mismatch['absoluteDifferenceBpm']:.4f}周期/分。"
            f"全域ピークは{'一致' if mismatch['globalBinMatches'] else '不一致'}、isNormalは{'一致' if mismatch['isNormalMatches'] else '不一致'}。整数Pythonとはこの補助出力も一致している。"
        )
    lines += [
        "",
        "列番号の完全一致だけでは、近いスコアを持つ候補の入れ替わりを評価できないため、選択列を全点Pythonのスコアで再評価した値も示す。",
        "比率は「回路が選んだ列の全点スコア ÷ 全点Pythonの最大スコア」。全点で適格条件を満たさない列のスコアは0。1に近いほどこの選択基準では近く、呼吸判定の正解率ではない。",
        "",
        "| 点数 | 全点でも適格な選択列 | 全点最大スコアに対する比率の平均 | 同じ選択列を全点で処理したPythonとの周波数差の平均 |",
        "|---|---:|---:|---:|",
    ]
    for m in summary:
        lines.append(
            f"| {m['sampleCount']} | {m['fullReferenceEligibleCount']}/5 | {m['meanFullReferenceScoreRatio']:.4f} | {m['fullPointsSameColumn']['meanAbsoluteDifferenceBpm']:.4f} |"
        )
    lines += [
        "",
        "## 前回の独立Python選択法との比較",
        "",
        "前回使用した、呼吸帯域のfloating-mean Lomb–Scargle適合度を重視するPython選択法も、今回と同じ実測ファイル・共有スケールで再計算した。",
        "この参照は元の全時刻点、実数演算、355点の周波数グリッドを使う。回路とは選択式・LSモデル・周波数刻みが異なるため、上の同式比較とは区別する。",
        "",
        "| 回路の点数 | 全点スペクトルPythonとの選択一致 | isNormal一致 | 周波数差の平均（周期/分） |",
        "|---|---:|---:|---:|",
    ]
    for m in summary:
        s = m["independentSpectralFullPoints"]
        lines.append(
            f"| {m['sampleCount']} | {s['selectionMatches']}/5 | {s['normalityMatches']}/5 | {s['meanAbsoluteDifferenceBpm']:.4f} |"
        )
    lines += [
        "",
        "Pythonが実際の呼吸をより正確に検出しているかは、正解ラベルがないため判定できない。この表も参照法への一致・差である。",
    ]
    lines += [
        "",
        "## 各CSIの出力",
        "",
        "| CSI | 点数 | 回路の選択列 | 全点Pythonの選択列 | 回路の全域ピークbin | 全点Pythonの全域ピークbin | 周波数差（周期/分） |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in names:
        for n in COUNTS:
            e = next(e for e in records[str(n)]["evaluation"]["results"] if e["name"] == name)
            c, f = e["circuit"], e["fullPython"]
            lines.append(
                f"| {name} | {n} | {c['selectedSubcarrier']} | {f['selectedSubcarrier']} | {c['globalPeakFrequencyBin']} | {f['globalPeakFrequencyBin']} | {e['differences']['fullPoints']['globalBpmAbsoluteDifference']:.4f} |"
            )
    lines += [
        "",
        "## 回路規模とwitness",
        "",
        "| 点数 | R1CS制約数 | 代表CSIのwitness計算（秒） |",
        "|---|---:|---:|",
    ]
    for m in summary:
        lines.append(f"| {m['sampleCount']} | {m['constraints']:,} | {m['representativeWitnessMs']/1000:.3f} |")
    lines += [
        "",
        "## 実際の証明・台帳計測",
        "",
        "代表実測CSI `csi_20260519_114943.csi` の全4,004候補を使用。各点数で実際にGroth16証明を作成し、両台帳に同じ証明を記録した。",
        "",
        "| 点数 | 公開信号数 | 証明処理（秒） | EVM記録確定（ms） | Fabric記録確定（ms） | EVM検証中央値（ms） | Fabric検証中央値（ms） | EVM記録gas |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in summary:
        lines.append(
            f"| {m['sampleCount']} | {m['publicSignalCount']} | {m['proveSeconds']:.3f} | {m['evmRecordMs']:.2f} | {m['fabricRecordMs']:.2f} | {m['evmVerifyMedianMs']:.2f} | {m['fabricVerifyMedianMs']:.2f} | {m['evmRecordGas']:,} |"
        )
    lines += [
        "",
        "初回測定値も別に示す。初回は未起動状態からのコールドスタートを保証する値ではない。",
        "",
        "| 点数 | EVM初回検証（ms） | Fabric初回検証（ms） | ローカルsnarkjs検証中央値（ms） |",
        "|---|---:|---:|---:|",
    ]
    for m in summary:
        ledger = records[str(m["sampleCount"])]["ledgers"]
        lines.append(
            f"| {m['sampleCount']} | {ledger['evm']['firstVerifyMs']:.2f} | {ledger['fabric']['firstVerifyMs']:.2f} | {m['localVerifyMedianMs']:.2f} |"
        )
    lines += [
        "",
        "- 記録は各条件1回の単発値。検証は初回＋追加10回、表は追加10回の中央値。独立した患者10人での測定ではない。",
        "- 証明処理時間はR1CS・witness・鍵の読み込み、鍵の群検査、全制約検査、証明生成、nativeローカル検証を含む。witness作成、鍵生成、デプロイは別。",
        "- EVMはGanache chainId=1337、Fabricはローカル2組織ネットワーク。Sepolia実測ではなく、Fabricインフラ費用も含まない。",
        "- EVMとFabricの差には、ローカル実装・ブロック生成設定・初回初期化の違いも含まれる。実測値をそのままSepolia対Fabricの性能差として扱わない。",
        "- 実稼働チャネルから取得したFabric設定はBatchTimeout=2秒、MaxMessageCount=10。今回の単発記録の待ち時間は、この設定の影響を受ける。",
        "- 検証はEVM eth_call / Fabric evaluateTransactionで、記録済み証明を台帳側で検証する照会時間。新たな検証トランザクションの確定時間ではない。",
        "- EVMのgas見積もりは記録タイマー外。記録時間は送信から成功receiptまで、ポーリング100ms。Fabricはendorse開始からcommit成功まで。",
        "- 実行順は96→128→64点。重いコンパイル・証明処理は直列実行し、台帳測定中に別点数のコンパイルを走らせない。",
        "- ホストはIntel Core i5-8500B・メモリ16GiB。証明処理中にOSのswap使用を確認したため、証明時間にはメモリ容量による影響も含まれる。環境と観測値はresults.jsonに保存。",
        "- 鍵生成はテスト用の単独セットアップ。既存台帳とは別の検証器・chaincode namespaceを使用。",
        "",
        "## 条件・限界",
        "",
        "各ファイルで観測区間・全候補列・量子化スケールを固定し、観測番号に対する等間隔間引きの点数のみ変更した。各点数の行集合は入れ子ではない。",
        "Python参照は電力を平均除去後、cos/sinを当てはめる現行回路と同じモデル。周波数ごとの定数項を追加する別のfloating-mean選択法とは区別する。",
        "全32binのグリッドは固定のため、点数を増やしても周波数の刻み自体は細かくならない。",
        "選択式のDは隣接する採用時刻点間の差分であり、点数を変えると比較する間隔も変わる。したがって、全点参照との差にはサンプリングとスコアの時間間隔依存性も含まれる。",
        "正解ラベルがないため、Pythonへの一致改善を実際の呼吸判定精度の向上と同一視しない。",
        "",
        "除外ファイル：",
        "",
    ]
    for d in datasets["datasets"]:
        if "excluded" in d:
            lines.append(f"- `{d['name']}`: {d['excluded']}")
    lines += [
        "",
        "詳細数値・取引ID・初回検証時間・繰り返し全測定値は [results.json](results.json)。",
        "実装・比較条件・再実行コマンドは [比較手順](../../sample-count-comparison.md)。",
        "コンパイル・証明・配備のログは [logs](logs/) に保存した（公開用コピーでは色コードと行末空白を除去）。",
        "",
        "![Pythonとの差](python-difference.png)",
        "",
        "![記録・検証時間](ledger-timings.png)",
        "",
    ]
    (args.output / "README.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
