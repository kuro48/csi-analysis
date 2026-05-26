"""
csi_main_to_zkp.py

PicoScenes .csi ファイルを受け取り、ベース行列（base_matrix.json）と合わせて
ZKP証明（Groth16）を生成して結果をJSONで保存する。

使い方:
    python csi_main_to_zkp.py <csi_file> --base base_matrix.json \\
        [--zkp-dir ../zkp] [--output zkp_result.json]

前提:
    - base_matrix.json: csi_base_to_zkp.py が生成したベース行列JSON
    - node / snarkjs がPATH上に存在すること
    - zkp/build/csi_full_similarity_js/csi_full_similarity.wasm が存在すること
    - zkp/keys/csi_full_similarity_final.zkey が存在すること

出力 JSON:
    {
        "proof": { ... },              // Groth16証明オブジェクト
        "publicSignals": ["0" or "1"], // isNormal
        "isNormal": bool,
        "num_freq_points": int,
        "num_subcarriers": int,
        "source_file": str,
        "base_file": str,
        "created_at": str              // ISO8601
    }
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import detrend, resample

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# パラメータ（csi_full_similarity.circom および PCAPAnalyzer と同期）  #
# ------------------------------------------------------------------ #

DOWNSAMPLE_INTERVAL_S: float = 0.01
FREQUENCY_BIN_STEP: float = 0.01

ZKP_FREQ_START: float = 0.0
ZKP_FREQ_END: float = 0.60
ZKP_SCALE: int = 10000
MAX_SUBCARRIERS: int = 245

EXPECTED_FREQ_POINTS: int = 31
EXPECTED_SUBCARRIERS: int = 245

GUARD_BANDS: list[tuple[int, int]] = [(-128, -122), (122, 127)]
PILOTS: list[int] = [-103, -75, -39, -11, 11, 39, 75, 103]


# ------------------------------------------------------------------ #
# Step 1: PicoScenes .csi → DataFrame                                #
# ------------------------------------------------------------------ #

def _select_subcarrier_positions(num_tones: int, max_subcarriers: int = MAX_SUBCARRIERS) -> np.ndarray:
    if num_tones <= max_subcarriers:
        return np.arange(num_tones)
    positions = np.round(np.linspace(0, num_tones - 1, max_subcarriers)).astype(int)
    return np.sort(np.unique(positions))


def load_csi_to_dataframe(file_path: str) -> pd.DataFrame:
    """PicoScenes Python Toolbox で .csi を DataFrame に変換する。"""
    try:
        from picoscenes import Picoscenes
    except ImportError as exc:
        raise RuntimeError(
            "picoscenes パッケージがインストールされていません。\n"
            "pip install 'picoscenes @ git+https://github.com/wifisensing/PicoScenes-Python-Toolbox.git' "
            "でインストールしてください。"
        ) from exc

    logger.info(f"PicoScenes ファイル読み込み開始: {file_path}")
    frames_obj = Picoscenes(file_path)
    raw_frames = getattr(frames_obj, "raw", None)
    if not raw_frames:
        raise ValueError("PicoScenes ファイルにフレームがありません")

    first = raw_frames[0]
    csi_info = first.get("CSI") or {}
    rx_info = first.get("RxSBasic") or {}

    num_tones = int(csi_info.get("numTones", 0))
    num_sts = int(rx_info.get("numSTS", 1) or 1)
    num_rx = int(rx_info.get("numRx", csi_info.get("numRx", 1)) or 1)
    subcarrier_indices = np.asarray(csi_info.get("SubcarrierIndex", []), dtype=np.int32)

    if num_tones <= 0 or subcarrier_indices.size != num_tones:
        raise ValueError("PicoScenes メタデータ不正: numTones / SubcarrierIndex の不一致")

    selected_positions = _select_subcarrier_positions(num_tones)
    selected_indices = subcarrier_indices[selected_positions]

    mag_array = np.empty((len(raw_frames), len(selected_positions)), dtype=np.float32)
    timestamps: list = []
    valid_count = 0
    fallback_ns: int | None = None

    for frame_idx, frame in enumerate(raw_frames):
        frame_csi = frame.get("CSI") or {}
        frame_rx = frame.get("RxSBasic") or {}
        mag = np.asarray(frame_csi.get("Mag", []), dtype=np.float32)

        if mag.size != num_tones * num_sts * num_rx:
            logger.debug(f"フレーム {frame_idx} をスキップ (Mag サイズ不正: {mag.size})")
            continue

        mag_matrix = mag.reshape((num_tones, num_sts, num_rx), order="F")
        tone_vector = mag_matrix[:, 0, 0]

        system_ns = frame_rx.get("systemns")
        if system_ns is None:
            if fallback_ns is None:
                fallback_ns = 0
            else:
                fallback_ns += int(DOWNSAMPLE_INTERVAL_S * 1_000_000_000)
            system_ns = fallback_ns

        mag_array[valid_count, :] = tone_vector[selected_positions]
        timestamps.append(pd.to_datetime(int(system_ns), unit="ns", errors="coerce"))
        valid_count += 1

    if valid_count == 0:
        raise ValueError("有効なフレームを変換できませんでした")

    col_names = [str(int(i)) for i in selected_indices]
    df = pd.DataFrame(mag_array[:valid_count], columns=col_names)
    df.insert(0, "timestamp", timestamps)

    logger.info(
        f"DataFrame 作成完了: フレーム={valid_count}, "
        f"サブキャリア={len(selected_indices)}, 元トーン数={num_tones}"
    )
    return df


# ------------------------------------------------------------------ #
# Step 2: 無効行削除                                                   #
# ------------------------------------------------------------------ #

def drop_invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    cleaned = df.dropna(subset=numeric_cols, how="any")
    return cleaned[~cleaned[numeric_cols].isin([np.inf, -np.inf]).any(axis=1)]


# ------------------------------------------------------------------ #
# Step 3: 不要サブキャリア削除                                          #
# ------------------------------------------------------------------ #

def remove_unnecessary_subcarriers(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    if "0" in df.columns:
        df = df.drop(columns=["0"])

    for start, end in GUARD_BANDS:
        cols = [str(i) for i in range(start, end + 1) if str(i) in df.columns]
        if cols:
            df = df.drop(columns=cols)

    pilot_cols = [str(i) for i in PILOTS if str(i) in df.columns]
    if pilot_cols:
        df = df.drop(columns=pilot_cols)

    remaining = len([c for c in df.columns if c.lstrip("-").isdigit()])
    logger.info(f"サブキャリアフィルタ後: {remaining} 列")
    return df


# ------------------------------------------------------------------ #
# Step 4: FFT適用                                                      #
# ------------------------------------------------------------------ #

def apply_fft(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    data_cols = [c for c in df.columns if c != "timestamp" and pd.api.types.is_numeric_dtype(df[c])]
    if not data_cols:
        return pd.DataFrame()

    target_fs = 1.0 / DOWNSAMPLE_INTERVAL_S

    if "timestamp" in df.columns and len(df) >= 2:
        ts = pd.to_datetime(df["timestamp"])
        duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
        actual_fs = (len(df) - 1) / duration_s if duration_s > 0 else target_fs
    else:
        actual_fs = target_fs

    resample_factor = actual_fs / target_fs
    logger.info(f"実サンプリングレート: {actual_fs:.2f} Hz, リサンプル係数: {resample_factor:.3f}")

    all_results: list[pd.DataFrame] = []
    for col in data_cols:
        signal = df[col].values.astype(np.float64)
        if len(signal) < 4:
            continue

        if abs(resample_factor - 1.0) > 0.05:
            n_target = max(4, int(round(len(signal) / resample_factor)))
            signal = resample(signal, n_target)

        signal = detrend(signal, type="linear")
        signal = signal * np.hanning(len(signal))

        yf = np.fft.rfft(signal)
        xf = np.fft.rfftfreq(len(signal), d=DOWNSAMPLE_INTERVAL_S)

        positive = xf > 0
        col_df = pd.DataFrame({"frequency": xf[positive], col: np.abs(yf[positive])})
        all_results.append(col_df.set_index("frequency"))

    if not all_results:
        return pd.DataFrame()

    merged = pd.concat(all_results, axis=1).reset_index()
    logger.info(f"FFT 完了: {len(data_cols)} サブキャリア, {len(merged)} 周波数ポイント")
    return drop_invalid_rows(merged)


# ------------------------------------------------------------------ #
# Step 5: 周波数ビン平均化                                              #
# ------------------------------------------------------------------ #

def average_by_frequency_bins(fft_df: pd.DataFrame) -> pd.DataFrame:
    if fft_df.empty or "frequency" not in fft_df.columns:
        return pd.DataFrame()

    max_freq = fft_df["frequency"].max()
    num_steps = int(max_freq / FREQUENCY_BIN_STEP)
    bins = [i * FREQUENCY_BIN_STEP for i in range(num_steps + 1)]

    df = fft_df.copy()
    df["freq_interval"] = pd.cut(df["frequency"], bins=bins, right=False, include_lowest=True)

    data_cols = [
        c for c in df.columns
        if c not in {"frequency", "freq_interval"}
        and pd.api.types.is_numeric_dtype(df[c])
    ]

    binned = df.groupby("freq_interval", observed=False)[data_cols].mean().reset_index()
    logger.info(f"周波数ビン平均化完了: {len(binned)} ビン")
    return binned


# ------------------------------------------------------------------ #
# Step 6: ZKP行列抽出                                                  #
# ------------------------------------------------------------------ #

def _interval_midpoint(value) -> float:
    if pd.isna(value):
        return 0.0
    if hasattr(value, "mid"):
        return float(value.mid)
    if isinstance(value, str):
        try:
            left, right = value.strip("[]()").split(",")
            return (float(left.strip()) + float(right.strip())) / 2.0
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def extract_zkp_matrix(binned_df: pd.DataFrame) -> list[list[int]]:
    """ビン平均済みDataFrameからZKP入力行列を生成する。"""
    if binned_df.empty:
        raise ValueError("ビン平均DataFrameが空です")

    df = binned_df.copy()
    df["_freq_mid"] = df["freq_interval"].apply(_interval_midpoint).astype(float)
    mask = (df["_freq_mid"] >= ZKP_FREQ_START) & (df["_freq_mid"] <= ZKP_FREQ_END)
    sub_df = df[mask]

    if sub_df.empty:
        raise ValueError(
            f"周波数帯域 {ZKP_FREQ_START}〜{ZKP_FREQ_END} Hz にデータがありません。"
            f"データ範囲: {df['_freq_mid'].min():.3f}〜{df['_freq_mid'].max():.3f} Hz"
        )

    subcarrier_cols = [
        c for c in sub_df.columns
        if c not in {"freq_interval", "_freq_mid"}
        and pd.api.types.is_numeric_dtype(sub_df[c])
    ]
    if not subcarrier_cols:
        raise ValueError("サブキャリア列が見つかりません")

    raw = sub_df[subcarrier_cols].to_numpy(dtype=np.float64)
    raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
    raw = np.maximum(raw, 0.0)

    col_min = raw.min(axis=0)
    col_max = raw.max(axis=0)
    col_range = np.where(col_max - col_min == 0.0, 1.0, col_max - col_min)
    normalized = (raw - col_min) / col_range

    matrix = [[int(v * ZKP_SCALE) for v in row] for row in normalized]

    logger.info(
        f"ZKP 行列抽出完了: {len(matrix)} 周波数ポイント × {len(subcarrier_cols)} サブキャリア"
    )
    return matrix


# ------------------------------------------------------------------ #
# Step 7: ZKP入力リサイズ                                              #
# ------------------------------------------------------------------ #

def resize_matrix(
    matrix: list[list[int]],
    target_rows: int,
    target_cols: int,
) -> list[list[int]]:
    """ZKP回路の期待サイズ（EXPECTED_FREQ_POINTS × EXPECTED_SUBCARRIERS）に合わせる。"""
    resized = []
    for i in range(target_rows):
        if i < len(matrix):
            row = [max(0, int(v)) for v in matrix[i][:target_cols]]
            row.extend([0] * (target_cols - len(row)))
        else:
            row = [0] * target_cols
        resized.append(row)
    return resized


# ------------------------------------------------------------------ #
# Step 8: Witness生成                                                  #
# ------------------------------------------------------------------ #

async def generate_witness(
    input_data: dict,
    zkp_dir: Path,
    temp_dir: Path,
) -> str:
    """snarkjs generate_witness.js でWitnessファイルを生成する。

    Returns:
        生成されたWitnessファイルパス（文字列）
    """
    wasm_file = zkp_dir / "build" / "csi_full_similarity_js" / "csi_full_similarity.wasm"
    generate_witness_js = zkp_dir / "build" / "csi_full_similarity_js" / "generate_witness.js"

    if not wasm_file.exists():
        raise FileNotFoundError(f"WASM ファイルが見つかりません: {wasm_file}")
    if not generate_witness_js.exists():
        raise FileNotFoundError(f"generate_witness.js が見つかりません: {generate_witness_js}")

    run_id = uuid.uuid4()
    input_file = temp_dir / f"csi_input_{run_id}.json"
    witness_file = temp_dir / f"csi_witness_{run_id}.wtns"

    with open(input_file, "w") as f:
        json.dump(input_data, f)

    cmd = ["node", str(generate_witness_js), str(wasm_file), str(input_file), str(witness_file)]

    env = os.environ.copy()
    env["NODE_OPTIONS"] = "--max-old-space-size=4096"

    logger.info("Witness 生成開始...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()

    input_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        stdout_msg = stdout.decode(errors="replace") if stdout else ""
        stderr_msg = stderr.decode(errors="replace") if stderr else ""
        raise RuntimeError(
            f"Witness 生成失敗 (returncode={proc.returncode})\n"
            f"stdout: {stdout_msg}\nstderr: {stderr_msg}"
        )

    logger.info(f"Witness 生成完了: {witness_file}")
    return str(witness_file)


# ------------------------------------------------------------------ #
# Step 9: Groth16証明生成                                              #
# ------------------------------------------------------------------ #

async def generate_groth16_proof(
    witness_file: str,
    zkp_dir: Path,
    temp_dir: Path,
) -> tuple[dict, list[str]]:
    """snarkjs groth16 prove でGroth16証明を生成する。

    Returns:
        (proof, publicSignals)
    """
    zkey_file = zkp_dir / "keys" / "csi_full_similarity_final.zkey"
    if not zkey_file.exists():
        raise FileNotFoundError(
            f"zkey ファイルが見つかりません: {zkey_file}\n"
            "cd zkp && npm run setup:full_similarity を実行してください。"
        )

    run_id = uuid.uuid4()
    proof_file = temp_dir / f"csi_proof_{run_id}.json"
    public_file = temp_dir / f"csi_public_{run_id}.json"

    cmd = [
        "snarkjs", "groth16", "prove",
        str(zkey_file),
        witness_file,
        str(proof_file),
        str(public_file),
    ]

    env = os.environ.copy()
    env["NODE_OPTIONS"] = "--max-old-space-size=4096"

    logger.info("Groth16 証明生成開始...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        stdout_msg = stdout.decode(errors="replace") if stdout else ""
        stderr_msg = stderr.decode(errors="replace") if stderr else ""
        raise RuntimeError(
            f"証明生成失敗 (returncode={proc.returncode})\n"
            f"stdout: {stdout_msg}\nstderr: {stderr_msg}"
        )

    with open(proof_file, "r") as f:
        proof = json.load(f)
    with open(public_file, "r") as f:
        public_signals = json.load(f)

    proof_file.unlink(missing_ok=True)
    public_file.unlink(missing_ok=True)

    logger.info("Groth16 証明生成完了")
    return proof, public_signals


# ------------------------------------------------------------------ #
# メインパイプライン                                                     #
# ------------------------------------------------------------------ #

def process_main_csi(csi_file: str) -> list[list[int]]:
    """メインCSIファイルを処理してZKP候補行列を返す。"""
    df = load_csi_to_dataframe(csi_file)
    df = drop_invalid_rows(df)
    if df.empty:
        raise ValueError("有効なデータ行がありません")

    df = remove_unnecessary_subcarriers(df)
    fft_df = apply_fft(df)
    if fft_df.empty:
        raise ValueError("FFT結果が空です")

    binned_df = average_by_frequency_bins(fft_df)
    return extract_zkp_matrix(binned_df)


async def run(csi_file: str, base_file: str, zkp_dir: Path, output_file: str) -> None:
    logger.info(f"=== メインCSI処理開始: {csi_file} ===")

    base_path = Path(base_file)
    if not base_path.exists():
        raise FileNotFoundError(f"ベース行列JSONが見つかりません: {base_path}")

    with open(base_path, "r", encoding="utf-8") as f:
        base_data = json.load(f)

    reference_matrix: list[list[int]] = base_data["matrix"]
    logger.info(
        f"ベース行列読み込み: {base_data['num_freq_points']} × {base_data['num_subcarriers']}"
    )

    candidate_matrix = process_main_csi(csi_file)
    logger.info(
        f"候補行列: {len(candidate_matrix)} × {len(candidate_matrix[0]) if candidate_matrix else 0}"
    )

    reference_matrix = resize_matrix(reference_matrix, EXPECTED_FREQ_POINTS, EXPECTED_SUBCARRIERS)
    candidate_matrix = resize_matrix(candidate_matrix, EXPECTED_FREQ_POINTS, EXPECTED_SUBCARRIERS)
    logger.info(f"リサイズ後: {EXPECTED_FREQ_POINTS} × {EXPECTED_SUBCARRIERS}")

    input_data = {
        "referenceMatrix": reference_matrix,
        "candidateMatrix": candidate_matrix,
    }

    temp_dir = Path(tempfile.gettempdir())
    witness_file = await generate_witness(input_data, zkp_dir, temp_dir)
    proof, public_signals = await generate_groth16_proof(witness_file, zkp_dir, temp_dir)
    Path(witness_file).unlink(missing_ok=True)

    is_normal = bool(int(public_signals[0])) if public_signals else False

    result = {
        "proof": proof,
        "publicSignals": public_signals,
        "isNormal": is_normal,
        "num_freq_points": EXPECTED_FREQ_POINTS,
        "num_subcarriers": EXPECTED_SUBCARRIERS,
        "source_file": str(Path(csi_file).resolve()),
        "base_file": str(base_path.resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    output_path = Path(output_file)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(
        f"=== 完了 ===\n"
        f"  isNormal: {is_normal}\n"
        f"  publicSignals: {public_signals}\n"
        f"  出力: {output_path.resolve()}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PicoScenes .csi → ZKP証明生成スクリプト"
    )
    parser.add_argument("csi_file", help=".csi ファイルパス")
    parser.add_argument(
        "--base", "-b",
        required=True,
        help="ベース行列JSONファイルパス（csi_base_to_zkp.py の出力）",
    )
    parser.add_argument(
        "--zkp-dir",
        default=None,
        help="zkp ディレクトリパス (デフォルト: スクリプトの ../zkp)",
    )
    parser.add_argument(
        "--output", "-o",
        default="zkp_result.json",
        help="出力JSONファイルパス (デフォルト: zkp_result.json)",
    )
    args = parser.parse_args()

    csi_path = Path(args.csi_file)
    if not csi_path.exists():
        logger.error(f"ファイルが見つかりません: {csi_path}")
        sys.exit(1)

    if args.zkp_dir:
        zkp_dir = Path(args.zkp_dir)
    else:
        script_dir = Path(__file__).resolve().parent
        zkp_dir = script_dir.parent / "zkp"

    if not zkp_dir.exists():
        logger.error(f"zkp ディレクトリが見つかりません: {zkp_dir}")
        sys.exit(1)

    try:
        asyncio.run(run(str(csi_path), args.base, zkp_dir, args.output))
    except Exception as exc:
        logger.error(f"処理失敗: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
