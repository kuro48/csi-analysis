"""
5-1.ipynb 由来の CSI 呼吸推定パイプライン。

処理の流れ（5-1.ipynb と同一）:
  1. CSI読み込み（PicoScenes .csi）
  2. 振幅抽出
  3. FFT/SNRで呼吸っぽいサブキャリアを選択
  4. バンドパスフィルタ
  5. PCAで呼吸候補成分を抽出
  6. VMDで呼吸成分を分解
  7. 呼吸数推定

呼吸あり/なし（正常）判定は Python 側では行わず、ZKP 回路
（zkp/circuits/csi_breathing_normality.circom）内で実施する。
本モジュールは回路の秘密入力（VMD呼吸成分の整数化時系列）を準備する。

【重要】「計算処理関数」セクションの関数は 5-1.ipynb から一切変更せずに
移植したもの。挙動を変える修正を加えないこと（描画関数のみ移植対象外）。
"""

import logging
import time
from collections import Counter
from contextlib import contextmanager
from typing import Any, Dict, List

import numpy as np
from scipy.signal import butter, filtfilt

logger = logging.getLogger(__name__)

try:
    from picoscenes import Picoscenes
except ImportError:  # pragma: no cover - 実行環境依存
    Picoscenes = None

try:
    from sklearn.decomposition import PCA
except ImportError:  # pragma: no cover - 実行環境依存
    PCA = None

try:
    from vmdpy import VMD
except ImportError:  # pragma: no cover - 実行環境依存
    VMD = None


# =========================================================
# 設定（5-1.ipynb と同一値）
# =========================================================
FS = 100

LOWCUT = 0.1
HIGHCUT = 1.0

N_SELECT = 256
PCA_COMPONENTS = 3

BPM_MIN = 6
BPM_MAX = 22

VMD_K = 5
VMD_ALPHA = 2000
VMD_TAU = 0
VMD_DC = 0
VMD_INIT = 1
VMD_TOL = 1e-7

# ZKP 回路入力仕様（csi_breathing_normality.circom と一致させること）
ZKP_TARGET_FS = 5.0
ZKP_T = 150
ZKP_SIGNAL_SCALE = 100


# =========================================================
# 計算処理関数（5-1.ipynb から無改変で移植 — 変更禁止）
# =========================================================
@contextmanager
def timer(label):
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"[TIME] {label}: {elapsed:.3f} 秒")


def load_csi_matrix(csi_file):
    """
    PicoScenesのCSIを読み込み、
    最も多いCSI長のデータだけを使って行列化する。
    """
    frames = Picoscenes(csi_file)

    csi_list = []
    lengths = []

    for frame in frames.raw:
        csi = frame.get("CSI")

        if csi is None:
            continue

        complex_csi = np.array(csi.get("CSI")).flatten()

        csi_list.append(complex_csi)
        lengths.append(len(complex_csi))

    if len(csi_list) == 0:
        raise ValueError("CSIデータが見つかりません。")

    length_counter = Counter(lengths)
    target_len = length_counter.most_common(1)[0][0]

    csi_matrix = np.array([
        csi for csi in csi_list
        if len(csi) == target_len
    ])

    print("CSI lengths:", length_counter)
    print("Selected TARGET_LEN:", target_len)
    print("CSI matrix shape:", csi_matrix.shape)

    return csi_matrix


def bandpass_filter(data, fs, lowcut, highcut, order=4):
    """
    Butterworthバンドパスフィルタ。
    指定した周波数帯域だけを通す。
    """
    nyq = fs / 2

    low = lowcut / nyq
    high = highcut / nyq

    if not (0 < low < high < 1):
        raise ValueError("lowcut / highcut / FS の設定を確認してください。")

    b, a = butter(order, [low, high], btype="band")
    filtered = filtfilt(b, a, data, axis=0)

    return filtered


def select_subcarriers_by_snr(amplitude_all, fs, lowcut, highcut, n_select):
    """
    各CSI indexについてSNRを計算し、
    SNRが高いサブキャリアを選択する。

    SNR = 呼吸帯域パワー / 高周波ノイズ帯域パワー
    """
    n_samples, n_subcarriers = amplitude_all.shape
    n_select = min(n_select, n_subcarriers)

    # 平均を引いてFFT
    amplitude_centered = amplitude_all - np.mean(amplitude_all, axis=0)

    freqs = np.fft.rfftfreq(n_samples, d=1 / fs)
    fft_values = np.fft.rfft(amplitude_centered, axis=0)
    power = np.abs(fft_values) ** 2

    # 呼吸帯域とノイズ帯域
    breath_band = (freqs >= lowcut) & (freqs <= highcut)
    noise_band = (freqs > highcut) & (freqs <= fs / 2)

    breath_power = np.sum(power[breath_band, :], axis=0)
    noise_power = np.sum(power[noise_band, :], axis=0)

    snr = breath_power / (noise_power + 1e-12)

    selected_indices = np.argsort(snr)[-n_select:]
    selected_indices = np.sort(selected_indices)

    selected_amplitude = amplitude_all[:, selected_indices]

    # 選択されたサブキャリアの呼吸帯域ピーク周波数を確認
    band_freqs = freqs[breath_band]
    selected_peak_freqs = []

    for idx in selected_indices:
        band_power = power[breath_band, idx]
        peak_freq = band_freqs[np.argmax(band_power)]
        selected_peak_freqs.append(peak_freq)

    selected_peak_freqs = np.array(selected_peak_freqs)

    print("Selected amplitude shape:", selected_amplitude.shape)
    print("Selected indices:", selected_indices)
    print("SNR shape:", snr.shape)
    print("Selected peak frequency range:")
    print(f"{selected_peak_freqs.min():.3f} Hz - {selected_peak_freqs.max():.3f} Hz")

    return selected_amplitude, selected_indices, snr


def respiration_score_fft(signal, fs, lowcut, highcut):
    """
    信号全体のうち、呼吸帯域に含まれるパワー割合を計算する。
    """
    signal = signal - np.mean(signal)

    freqs = np.fft.rfftfreq(len(signal), d=1 / fs)
    power = np.abs(np.fft.rfft(signal)) ** 2

    breath_band = (freqs >= lowcut) & (freqs <= highcut)

    breath_power = np.sum(power[breath_band])
    total_power = np.sum(power)

    score = breath_power / (total_power + 1e-12)

    return score


def select_respiration_pc(principal_components, fs, lowcut, highcut):
    """
    PC1〜PC3の中から、
    呼吸帯域パワー割合が最も大きいPCを選ぶ。
    """
    scores = []

    for i in range(principal_components.shape[1]):
        score = respiration_score_fft(
            principal_components[:, i],
            fs,
            lowcut,
            highcut
        )
        scores.append(score)

    best_idx = int(np.argmax(scores))
    respiration_pc = principal_components[:, best_idx]

    print("Respiration FFT scores:")
    for i, score in enumerate(scores):
        print(f"PC{i + 1}: {score:.4f}")

    print(f"Selected respiration component before VMD: PC{best_idx + 1}")

    return respiration_pc, best_idx, scores


def estimate_breathing_rate_by_vmd_global_peak(
    signal,
    fs,
    bpm_min,
    bpm_max,
    K,
    alpha,
    tau,
    DC,
    init,
    tol
):
    """
    VMDで信号をK個のモードに分解し、
    各モードの最大ピーク周波数が呼吸範囲内かを評価する。
    """
    signal = signal - np.mean(signal)

    vmd_modes, _, _ = VMD(
        signal,
        alpha,
        tau,
        K,
        DC,
        init,
        tol
    )

    low_hz = bpm_min / 60
    high_hz = bpm_max / 60

    mode_infos = []

    for i in range(K):
        mode = vmd_modes[i, :]
        mode_centered = mode - np.mean(mode)

        freqs = np.fft.rfftfreq(len(mode_centered), d=1 / fs)
        power = np.abs(np.fft.rfft(mode_centered)) ** 2

        # DC成分を除いて最大ピークを探す
        if len(power) > 1:
            global_peak_idx = np.argmax(power[1:]) + 1
        else:
            global_peak_idx = 0

        global_peak_freq = freqs[global_peak_idx]
        global_peak_bpm = global_peak_freq * 60
        global_peak_power = power[global_peak_idx]

        total_power = np.sum(power)
        global_peak_ratio = global_peak_power / (total_power + 1e-12)

        is_valid = low_hz <= global_peak_freq <= high_hz

        mode_infos.append({
            "mode_index": i,
            "mode": mode,
            "freqs": freqs,
            "power": power,
            "global_peak_freq": global_peak_freq,
            "global_peak_bpm": global_peak_bpm,
            "global_peak_power": global_peak_power,
            "global_peak_ratio": global_peak_ratio,
            "is_valid": is_valid
        })

    valid_modes = [
        info for info in mode_infos
        if info["is_valid"]
    ]

    if len(valid_modes) > 0:
        best_info = max(valid_modes, key=lambda x: x["global_peak_ratio"])
    else:
        best_info = max(mode_infos, key=lambda x: x["global_peak_ratio"])
        print("⚠️ 呼吸範囲内にglobal peakを持つModeがありません。")

    return vmd_modes, mode_infos, best_info


# =========================================================
# ZKP 回路入力の準備（プラットフォーム統合用の新規コード）
# =========================================================
def prepare_breathing_zkp_input(
    vmd_mode: np.ndarray,
    fs: float = FS,
    target_fs: float = ZKP_TARGET_FS,
    t_target: int = ZKP_T,
    scale: int = ZKP_SIGNAL_SCALE,
) -> List[int]:
    """選択された VMD 呼吸成分から ZKP 回路の秘密入力 vmd[T] を作る。

    5-1.ipynb の判定（VMDモードのFFTピーク周波数が呼吸範囲内か）を
    回路内 DFT で再現できるよう、以下を行う:
      1. target_fs へダウンサンプリング（バンドパス済みのため単純間引きで安全）
      2. 先頭 t_target サンプルを使用（不足分はゼロパディング）
      3. 平均を引いてゼロ中心化（5-1.ipynb の FFT 前処理と同じ）
      4. 最大絶対値で正規化し ±scale の整数へ丸め
    """
    if fs <= 0 or target_fs <= 0 or fs < target_fs:
        raise ValueError("fs / target_fs の設定を確認してください。")

    step = int(round(fs / target_fs))
    signal = np.asarray(vmd_mode, dtype=np.float64)[::step]

    if len(signal) >= t_target:
        signal = signal[:t_target]
    else:
        signal = np.pad(signal, (0, t_target - len(signal)))

    signal = signal - np.mean(signal)

    max_abs = np.max(np.abs(signal))
    if max_abs > 0:
        signal = signal / max_abs * scale

    return [int(round(float(v))) for v in signal]


# =========================================================
# パイプライン実行（5-1.ipynb の main() と同じ手順、描画・判定を除く）
# =========================================================
def _check_dependencies(require_loader: bool) -> None:
    missing = []
    if require_loader and Picoscenes is None:
        missing.append("picoscenes")
    if PCA is None:
        missing.append("scikit-learn")
    if VMD is None:
        missing.append("vmdpy")
    if missing:
        raise RuntimeError(
            f"呼吸推定パイプラインに必要なパッケージが未インストールです: {', '.join(missing)}"
        )


def run_breathing_pipeline_from_matrix(csi_matrix: np.ndarray) -> Dict[str, Any]:
    """複素CSI行列 [n_samples × n_subcarriers] に 5-1.ipynb の処理を適用する。

    Returns:
        呼吸推定サマリと ZKP 回路入力（zkp_input）を含む辞書。
        呼吸あり/なし判定は含まない（ZKP 回路側で行う）。
    """
    _check_dependencies(require_loader=False)

    total_start = time.perf_counter()

    # 2. 振幅抽出
    with timer("振幅抽出"):
        amplitude_all = np.abs(csi_matrix)
        print("Amplitude shape:", amplitude_all.shape)

    # 3. サブキャリア選択
    with timer("FFT/SNRによるサブキャリア選択"):
        selected_amplitude, selected_indices, snr = select_subcarriers_by_snr(
            amplitude_all=amplitude_all,
            fs=FS,
            lowcut=LOWCUT,
            highcut=HIGHCUT,
            n_select=N_SELECT
        )

    # 4. バンドパスフィルタ
    with timer("選択サブキャリアへのバンドパス"):
        pca_input = bandpass_filter(
            selected_amplitude,
            fs=FS,
            lowcut=LOWCUT,
            highcut=HIGHCUT,
            order=4
        )
        print("PCA input shape:", pca_input.shape)

    # 5. PCA
    with timer("PCA"):
        pca = PCA(n_components=PCA_COMPONENTS)
        principal_components = pca.fit_transform(pca_input)

        print("PCA output shape:", principal_components.shape)
        print("Explained variance ratio:")
        print(pca.explained_variance_ratio_)

    # 6. 呼吸PC選択
    with timer("FFTによる呼吸PC選択"):
        respiration_pc, best_pc_idx, pc_scores = select_respiration_pc(
            principal_components,
            fs=FS,
            lowcut=LOWCUT,
            highcut=HIGHCUT
        )

    # 7. VMD
    with timer("VMDによる呼吸数推定"):
        vmd_modes, mode_infos, best_vmd_info = estimate_breathing_rate_by_vmd_global_peak(
            signal=respiration_pc,
            fs=FS,
            bpm_min=BPM_MIN,
            bpm_max=BPM_MAX,
            K=VMD_K,
            alpha=VMD_ALPHA,
            tau=VMD_TAU,
            DC=VMD_DC,
            init=VMD_INIT,
            tol=VMD_TOL
        )

    vmd_respiration = best_vmd_info["mode"]
    peak_freq = best_vmd_info["global_peak_freq"]
    breathing_rate_bpm = best_vmd_info["global_peak_bpm"]

    # 8. ZKP 回路入力の準備（正常判定は回路内で行う）
    zkp_input = prepare_breathing_zkp_input(vmd_respiration)

    elapsed = time.perf_counter() - total_start
    logger.info(
        "Breathing pipeline completed: bpm=%.2f, PC%d, VMD Mode %d, %.3fs",
        breathing_rate_bpm, best_pc_idx + 1, best_vmd_info["mode_index"] + 1, elapsed,
    )

    return {
        "respiration_waveform": [float(v) for v in vmd_respiration],
        "breathing_rate_bpm": float(breathing_rate_bpm),
        "peak_freq_hz": float(peak_freq),
        "selected_pc": int(best_pc_idx + 1),
        "pc_scores": [float(s) for s in pc_scores],
        "selected_vmd_mode": int(best_vmd_info["mode_index"] + 1),
        "vmd_mode_summaries": [
            {
                "mode": int(info["mode_index"] + 1),
                "global_peak_freq_hz": float(info["global_peak_freq"]),
                "global_peak_bpm": float(info["global_peak_bpm"]),
                "global_peak_ratio": float(info["global_peak_ratio"]),
                "is_valid": bool(info["is_valid"]),
            }
            for info in mode_infos
        ],
        "n_samples": int(amplitude_all.shape[0]),
        "n_subcarriers_total": int(amplitude_all.shape[1]),
        "n_subcarriers_selected": int(selected_amplitude.shape[1]),
        "bpm_range": {"min": BPM_MIN, "max": BPM_MAX},
        "processing_time_seconds": float(elapsed),
        "zkp_input": zkp_input,
    }


def run_breathing_pipeline(csi_file: str) -> Dict[str, Any]:
    """PicoScenes .csi ファイルに 5-1.ipynb の一連の処理を適用する。"""
    _check_dependencies(require_loader=True)

    # 1. CSI読み込み
    with timer("CSI読み込み・行列作成"):
        csi_matrix = load_csi_matrix(csi_file)

    return run_breathing_pipeline_from_matrix(csi_matrix)
