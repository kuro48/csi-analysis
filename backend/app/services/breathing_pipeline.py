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

import hashlib
import logging
import struct
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

# 証明書回路入力仕様（csi_breathing_certificate.circom と一致させること）
ZKP_CERT_K = VMD_K  # 回路 K と一致（VMD モード数）
ZKP_CERT_SIGNAL_SCALE = 100  # 回路 SIGNAL_SCALE と一致（signal 目標スケール）
ZKP_CERT_MODE_MAX_ABS = 1000  # 回路 MODE_MAX_ABS と一致（モード絶対値上限）
ZKP_CERT_RECON_ERR_RATIO = 0.5  # 回路 RECON_ERR_NUM/RECON_ERR_DEN と一致（再構成誤差エネルギー許容比）
ZKP_CERT_NARROW_RATIO = 0.05  # 回路 NARROW_NUM/NARROW_DEN と一致（narrowband ピーク比下限）


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

    csi_matrix = np.array([csi for csi in csi_list if len(csi) == target_len])

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
        score = respiration_score_fft(principal_components[:, i], fs, lowcut, highcut)
        scores.append(score)

    best_idx = int(np.argmax(scores))
    respiration_pc = principal_components[:, best_idx]

    print("Respiration FFT scores:")
    for i, score in enumerate(scores):
        print(f"PC{i + 1}: {score:.4f}")

    print(f"Selected respiration component before VMD: PC{best_idx + 1}")

    return respiration_pc, best_idx, scores


def estimate_breathing_rate_by_vmd_global_peak(signal, fs, bpm_min, bpm_max, K, alpha, tau, DC, init, tol):
    """
    VMDで信号をK個のモードに分解し、
    各モードの最大ピーク周波数が呼吸範囲内かを評価する。
    """
    signal = signal - np.mean(signal)

    vmd_modes, _, _ = VMD(signal, alpha, tau, K, DC, init, tol)

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

        mode_infos.append(
            {
                "mode_index": i,
                "mode": mode,
                "freqs": freqs,
                "power": power,
                "global_peak_freq": global_peak_freq,
                "global_peak_bpm": global_peak_bpm,
                "global_peak_power": global_peak_power,
                "global_peak_ratio": global_peak_ratio,
                "is_valid": is_valid,
            }
        )

    valid_modes = [info for info in mode_infos if info["is_valid"]]

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


def prepare_zkvm_input(
    csi_matrix: np.ndarray,
    scale: int = 10_000,
) -> Dict[str, Any]:
    """zkVM 内の 5-1 固定小数点パイプラインへ渡す CSI 振幅行列を作る。

    PicoScenes バイナリの構造解析はホスト側に残し、複素 CSI から後の
    振幅抽出→SNR選択→バンドパス→PCA→VMD→呼吸判定を guest で再実行する。
    入力は全体の最大振幅で固定小数点化し、SHA-256 コミットメントを
    公開 journal と照合できるようにする。
    """
    matrix = np.asarray(csi_matrix)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("csi_matrix は空でない 2 次元行列である必要があります")
    if scale <= 0:
        raise ValueError("scale は正の整数である必要があります")

    amplitudes = np.abs(matrix).astype(np.float64)
    if not np.all(np.isfinite(amplitudes)):
        raise ValueError("CSI 振幅に非有限値が含まれています")
    max_amplitude = float(np.max(amplitudes))
    if max_amplitude <= 0:
        raise ValueError("CSI 振幅が全てゼロです")

    quantized = np.rint(amplitudes / max_amplitude * scale).astype(np.int64)
    samples, subcarriers = quantized.shape
    flattened = [int(value) for value in quantized.ravel(order="C")]

    digest = hashlib.sha256()
    digest.update(struct.pack("<III", int(samples), int(subcarriers), int(scale)))
    for value in flattened:
        digest.update(struct.pack("<i", value))

    return {
        "samples": int(samples),
        "subcarriers": int(subcarriers),
        "amplitudes": flattened,
        "scale": int(scale),
        "sample_rate_hz": FS,
        "bpm_min": BPM_MIN,
        "bpm_max": BPM_MAX,
        "input_commitment": digest.hexdigest(),
        "algorithm_version": "5-1-fixed-v1",
    }


def prepare_breathing_certificate_input(
    respiration_pc: np.ndarray,
    vmd_modes: np.ndarray,
    selected_mode_index: int,
    fs: float = FS,
    target_fs: float = ZKP_TARGET_FS,
    t_target: int = ZKP_T,
    signal_scale: int = ZKP_CERT_SIGNAL_SCALE,
    mode_max_abs: int = ZKP_CERT_MODE_MAX_ABS,
) -> Dict[str, Any]:
    """証明書回路 csi_breathing_certificate.circom の秘密入力を作る。

    docs/ZKP_PIPELINE_EXTENSION_IDEAS.md テーマ1・案A の入力準備。

    再構成性 Σ_k modes[k][t] ≈ vmdInput[t] を整数領域で保つため、VMD 入力信号と
    全モードに *同一* のスケール係数を適用する（単一モードを個別正規化する
    prepare_breathing_zkp_input とは異なる）。

    処理:
      1. VMD 入力（respiration_pc）を中心化
         （estimate_breathing_rate_by_vmd_global_peak と同一の前処理）。
         モードは VMD が中心化済み信号を分解した出力なので再中心化しない。
      2. target_fs へ間引き、先頭 t_target サンプルを使用（不足分ゼロパディング）。
      3. signal ≤ signal_scale かつ 全モード ≤ mode_max_abs を保証する共通スケール係数を
         求め、signal と全モードへ一括適用して整数化。
      4. sel は選択モードを指す one-hot。

    Returns:
        {"vmdInput": [T], "modes": [K][T], "sel": [K], "diagnostics": {...}}
        diagnostics は回路のハード制約・判定に対応する参考値。
    """
    modes = np.asarray(vmd_modes, dtype=np.float64)
    if modes.ndim != 2:
        raise ValueError("vmd_modes は [K, N] の2次元配列である必要があります")

    k_modes = modes.shape[0]
    if not (0 <= selected_mode_index < k_modes):
        raise ValueError("selected_mode_index が範囲外です")
    if fs <= 0 or target_fs <= 0 or fs < target_fs:
        raise ValueError("fs / target_fs の設定を確認してください。")

    step = int(round(fs / target_fs))

    # VMD 入力の中心化（VMD はこの中心化済み信号を分解している）
    sig = np.asarray(respiration_pc, dtype=np.float64)
    sig = sig - np.mean(sig)

    def downsample(arr: np.ndarray) -> np.ndarray:
        d = np.asarray(arr, dtype=np.float64)[::step]
        if len(d) >= t_target:
            return d[:t_target]
        return np.pad(d, (0, t_target - len(d)))

    sig_ds = downsample(sig)
    modes_ds = np.vstack([downsample(modes[k]) for k in range(k_modes)])

    sig_max = float(np.max(np.abs(sig_ds)))
    mode_max = float(np.max(np.abs(modes_ds)))
    if sig_max <= 0:
        raise ValueError("VMD 入力信号が全てゼロです")

    # signal ≤ signal_scale を基本とし、モードが上限を超える場合のみ更に縮小
    factor = signal_scale / sig_max
    if mode_max > 0:
        factor = min(factor, mode_max_abs / mode_max)

    vmd_input_int = [int(round(float(v) * factor)) for v in sig_ds]
    modes_int = [[int(round(float(v) * factor)) for v in modes_ds[k]] for k in range(k_modes)]
    sel = [1 if k == selected_mode_index else 0 for k in range(k_modes)]

    # ---- 診断メトリクス（回路のハード制約・判定に対応する参考値） ----
    sig_arr = np.array(vmd_input_int, dtype=np.float64)
    recon = np.sum(np.array(modes_int, dtype=np.float64), axis=0)
    err_energy = float(np.sum((recon - sig_arr) ** 2))
    sig_energy = float(np.sum(sig_arr**2))
    recon_error_ratio = err_energy / sig_energy if sig_energy > 0 else float("inf")

    sel_mode = np.array(modes_int[selected_mode_index], dtype=np.float64)
    sel_mode = sel_mode - np.mean(sel_mode)
    power = np.abs(np.fft.rfft(sel_mode)) ** 2
    if len(power) > 1:
        peak_power = float(np.max(power[1:]))  # DC を除いたグローバルピーク（5-1と同様）
    else:
        peak_power = 0.0
    narrow_ratio = peak_power / (float(np.sum(power)) + 1e-12)

    max_mode_abs = int(np.max(np.abs(np.array(modes_int)))) if k_modes else 0

    diagnostics = {
        "recon_error_ratio": recon_error_ratio,
        "recon_error_ratio_threshold": ZKP_CERT_RECON_ERR_RATIO,
        "recon_ok": recon_error_ratio <= ZKP_CERT_RECON_ERR_RATIO,
        "narrow_ratio": narrow_ratio,
        "narrow_ratio_threshold": ZKP_CERT_NARROW_RATIO,
        "narrow_ok": narrow_ratio >= ZKP_CERT_NARROW_RATIO,
        "max_mode_abs": max_mode_abs,
        "mode_max_abs_limit": mode_max_abs,
        "scale_factor": float(factor),
    }

    if not diagnostics["recon_ok"]:
        logger.warning(
            "Certificate input: reconstruction error ratio %.3f exceeds threshold %.3f "
            "(circuit will reject). Consider raising VMD_K or the circuit RECON_ERR ratio.",
            recon_error_ratio,
            ZKP_CERT_RECON_ERR_RATIO,
        )

    return {
        "vmdInput": vmd_input_int,
        "modes": modes_int,
        "sel": sel,
        "diagnostics": diagnostics,
    }


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
        raise RuntimeError(f"呼吸推定パイプラインに必要なパッケージが未インストールです: {', '.join(missing)}")


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
            amplitude_all=amplitude_all, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT, n_select=N_SELECT
        )

    # 4. バンドパスフィルタ
    with timer("選択サブキャリアへのバンドパス"):
        pca_input = bandpass_filter(selected_amplitude, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT, order=4)
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
            principal_components, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT
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
            tol=VMD_TOL,
        )

    vmd_respiration = best_vmd_info["mode"]
    peak_freq = best_vmd_info["global_peak_freq"]
    breathing_rate_bpm = best_vmd_info["global_peak_bpm"]

    # 8. ZKP 回路入力の準備（正常判定は回路内で行う）
    zkp_input = prepare_breathing_zkp_input(vmd_respiration)

    # 8b. 証明書回路入力の準備（案A: 全モード＋入力信号で再構成性も証明）
    certificate_input = prepare_breathing_certificate_input(
        respiration_pc=respiration_pc,
        vmd_modes=vmd_modes,
        selected_mode_index=int(best_vmd_info["mode_index"]),
    )

    # zkVM は同じ生 CSI 行列に対して数値パイプライン全体を再実行する。
    zkvm_input = prepare_zkvm_input(csi_matrix)

    elapsed = time.perf_counter() - total_start
    logger.info(
        "Breathing pipeline completed: bpm=%.2f, PC%d, VMD Mode %d, %.3fs",
        breathing_rate_bpm,
        best_pc_idx + 1,
        best_vmd_info["mode_index"] + 1,
        elapsed,
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
        "certificate_input": certificate_input,
        "zkvm_input": zkvm_input,
    }


def run_breathing_pipeline(csi_file: str) -> Dict[str, Any]:
    """PicoScenes .csi ファイルに 5-1.ipynb の一連の処理を適用する。"""
    _check_dependencies(require_loader=True)

    # 1. CSI読み込み
    with timer("CSI読み込み・行列作成"):
        csi_matrix = load_csi_matrix(csi_file)

    return run_breathing_pipeline_from_matrix(csi_matrix)
