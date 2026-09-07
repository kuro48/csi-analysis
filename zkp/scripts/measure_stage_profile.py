#!/usr/bin/env python3
"""Circom回路の段階別プロファイルを実測して build/stage_profile.json に書き出す。

Groth16は全制約を一括で証明するため、1回の証明から段階ごとの所要時間を
取り出すことはできない。そこで回路を段階の境界で切り詰めた版を個別に
コンパイルし、累積制約数の差分から各段階の寄与を求める。

証明生成時間は入力値に依存せず回路構造だけで決まるため、ここで一度測った
プロファイルは以降のすべての解析に対して有効。実行時は総時間だけを実測し、
このプロファイルの制約数比で内訳に按分する。

使い方:
    python3 scripts/measure_stage_profile.py            # 制約数のみ（高速）
    python3 scripts/measure_stage_profile.py --overhead # 固定オーバーヘッドも実測
"""

import argparse
import json
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ZKP_DIR = Path(__file__).resolve().parent.parent
CIRCUITS = ZKP_DIR / "circuits"
BUILD = ZKP_DIR / "build"
KEYS = ZKP_DIR / "keys"
# build/ は .gitignore 対象なので、回路と一緒に追跡されるディレクトリへ出力する。
# 制約数は回路ソースだけで決まる機械非依存の値で、固定オーバーヘッドのみ実行環境に依存する。
PROFILE_PATH = ZKP_DIR / "profiles" / "stage_profile.json"

CIRCUIT_NAME = "csi_breathing_certificate"

# 回路内の「// ===== N. ... =====」で区切られた素の段階を、意味のある処理単位へまとめる。
# 段階1(5制約)や段階7(20制約)は単独では計測ノイズに埋もれるため隣接段と束ねる。
STAGE_GROUPS = [
    {"key": "vmd_verify", "label": "VMD検証", "through": 3,
     "description": "sel one-hot・モード合成・再構成性チェック"},
    {"key": "dft", "label": "DFTパワースペクトル", "through": 4,
     "description": "選択モードの周波数パワー算出"},
    {"key": "argmax", "label": "argmaxピーク探索", "through": 5,
     "description": "全周波数ビンの逐次比較によるピーク特定"},
    {"key": "decision", "label": "正常判定", "through": 7,
     "description": "narrowband判定と正常帯域判定"},
]

# 切り詰め版が最適化で消えないよう、その段階の終端信号に依存する出力を与える。
TERMINAL_OUTPUT = {
    1: "isNormal <== sel[0];",
    2: "isNormal <== selectedMode[T-1];",
    3: "isNormal <== reconOk.out;",
    4: "isNormal <== totalPow;",
    5: "isNormal <== maxPow[NUM_FREQ-1] + maxIdx[NUM_FREQ-1];",
    6: "isNormal <== narrowOk.out;",
    7: None,
}


def build_variants(work_dir: Path) -> list[int]:
    """段階ごとに切り詰めた回路を work_dir に生成し、段階番号の一覧を返す。"""
    src = (CIRCUITS / f"{CIRCUIT_NAME}.circom").read_text().split("\n")

    marks: dict[int, int] = {}
    for lineno, line in enumerate(src, 1):
        m = re.match(r"//\s*=====\s*(\d+)\.", line.strip())
        if m:
            marks[int(m.group(1))] = lineno
    if not marks:
        raise SystemExit("段階マーカー（// ===== N. ...）が見つかりません")

    body_end = next(i for i, l in enumerate(src, 1) if "isNormal <== inRange" in l)
    main_line = next(i for i, l in enumerate(src, 1) if l.startswith("component main"))

    prefix = src[: marks[1] - 1]
    last = max(marks)

    work_dir.mkdir(parents=True, exist_ok=True)
    for n in sorted(marks):
        cut = marks[n + 1] - 1 if n < last else body_end
        lines = prefix + src[marks[1] - 1 : cut]
        extra = TERMINAL_OUTPUT.get(n)
        if extra:
            lines.append("    " + extra)
        lines += ["}", "", src[main_line - 1]]
        (work_dir / f"stage{n}.circom").write_text("\n".join(lines))
    return sorted(marks)


def compile_variant(work_dir: Path, n: int) -> int:
    """切り詰め版をコンパイルし、累積の総制約数（非線形＋線形）を返す。"""
    result = subprocess.run(
        ["circom", f"stage{n}.circom", "--r1cs", "-o", str(work_dir),
         "-l", str(ZKP_DIR / "node_modules")],
        cwd=work_dir, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"stage{n} のコンパイルに失敗しました:\n{result.stdout}\n{result.stderr}")

    nonlinear = int(re.search(r"non-linear constraints: (\d+)", result.stdout).group(1))
    linear = int(re.search(r"^linear constraints: (\d+)", result.stdout, re.M).group(1))
    return nonlinear + linear


def measure_overhead(work_dir: Path, repeats: int = 9) -> float:
    """最小回路の証明時間＝制約数に依存しない固定費（プロセス起動とzkey読み込み）。"""
    ptau = KEYS / "powersOfTau28_hez_final_19.ptau"
    if not ptau.exists():
        raise SystemExit(f"{ptau} が見つかりません")

    subprocess.run(["circom", "stage1.circom", "--r1cs", "--wasm", "-o", str(work_dir),
                    "-l", str(ZKP_DIR / "node_modules")],
                   cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["snarkjs", "groth16", "setup", "stage1.r1cs", str(ptau), "ov_0.zkey"],
                   cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["snarkjs", "zkey", "contribute", "ov_0.zkey", "ov.zkey", "-n=profile"],
                   cwd=work_dir, check=True, capture_output=True, input=b"profile-entropy\n")

    sample = {"vmdInput": ["0"] * 300, "modes": [["0"] * 300 for _ in range(5)],
              "sel": ["1", "0", "0", "0", "0"]}
    (work_dir / "ov_in.json").write_text(json.dumps(sample))
    subprocess.run(["node", "stage1_js/generate_witness.js", "stage1_js/stage1.wasm",
                    "ov_in.json", "ov.wtns"],
                   cwd=work_dir, check=True, capture_output=True)

    timings = []
    for _ in range(repeats):
        started = time.perf_counter()
        subprocess.run(["snarkjs", "groth16", "prove", "ov.zkey", "ov.wtns", "ov_p.json", "ov_pub.json"],
                       cwd=work_dir, check=True, capture_output=True)
        timings.append((time.perf_counter() - started) * 1000)
    return statistics.median(timings)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overhead", action="store_true",
                        help="固定オーバーヘッドも実測する（trusted setupを伴うため時間がかかる）")
    parser.add_argument("--work-dir", default="/tmp/stage_profile")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    stages = build_variants(work_dir)

    cumulative = {n: compile_variant(work_dir, n) for n in stages}
    total = cumulative[max(stages)]

    entries = []
    previous = 0
    for group in STAGE_GROUPS:
        upto = cumulative[group["through"]]
        entries.append({
            "key": group["key"],
            "label": group["label"],
            "description": group["description"],
            "constraints": upto - previous,
        })
        previous = upto

    profile = {
        "circuitName": CIRCUIT_NAME,
        "totalConstraints": total,
        "stages": entries,
        "measuredAt": datetime.now(timezone.utc).isoformat(),
    }

    if args.overhead:
        profile["fixedOverheadMs"] = round(measure_overhead(work_dir), 1)

    if PROFILE_PATH.exists():
        existing = json.loads(PROFILE_PATH.read_text())
        # --overhead なしで実行したときに、前回測った固定費を捨てない。
        if "fixedOverheadMs" not in profile and existing.get("circuitName") == CIRCUIT_NAME:
            if "fixedOverheadMs" in existing:
                profile["fixedOverheadMs"] = existing["fixedOverheadMs"]

    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n")

    print(f"総制約数: {total}")
    for entry in entries:
        share = entry["constraints"] / total * 100
        print(f"  {entry['label']:<20} {entry['constraints']:>7} 制約  ({share:5.1f}%)")
    if "fixedOverheadMs" in profile:
        print(f"固定オーバーヘッド: {profile['fixedOverheadMs']} ms")
    print(f"→ {PROFILE_PATH}")


if __name__ == "__main__":
    main()
