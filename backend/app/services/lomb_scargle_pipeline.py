"""既存CSI前処理のPCA出力へLomb--Scargleだけを適用する。

CSI読込、振幅化、SNRサブキャリア選択、バンドパス、PCAは
``breathing_pipeline`` が一度だけ実行する。本モジュールは、そのPCA出力と
同じパケットの不均一タイムスタンプを受け取り、ピリオドグラムと呼吸数を求める。

Lomb--Scargle変換そのものはPythonで実行する。Circomへ渡すのは固定小数点化した
ピリオドグラムであり、回路が証明する範囲はPC選択、argmax、入力範囲、
正常BPM帯域判定である。
"""

import logging
import time
from typing import Any, Dict, List, Mapping, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    from scipy.signal import lombscargle
except ImportError:  # pragma: no cover - 実行環境依存
    lombscargle = None


PCA_COMPONENTS = 3
BPM_MIN = 6.0
BPM_MAX = 40.0

FREQ_MIN_HZ = 0.05
FREQ_MAX_HZ = 1.5
N_FREQUENCIES = 1000
PERIODOGRAM_POWER_SCALE = 1_000_000

FREQUENCIES_HZ = np.linspace(FREQ_MIN_HZ, FREQ_MAX_HZ, N_FREQUENCIES)
NORMAL_FREQUENCY_MASK = (FREQUENCIES_HZ * 60 >= BPM_MIN) & (FREQUENCIES_HZ * 60 <= BPM_MAX)


def _sort_and_deduplicate(
    principal_components: np.ndarray,
    timestamps_ns: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, int]:
    """PCA行と時刻の対応を保ったまま時刻順に並べ、重複時刻を除く。"""

    components = np.asarray(principal_components, dtype=np.float64)
    timestamps = np.asarray(timestamps_ns, dtype=np.int64).reshape(-1)
    if components.ndim != 2 or components.shape[0] != timestamps.size:
        raise ValueError("PCA出力の行数とタイムスタンプ数が一致していません")
    if components.shape[0] < 4:
        raise ValueError("Lomb-Scargle解析には4パケット以上が必要です")
    if components.shape[1] < 1:
        raise ValueError("Lomb-Scargle解析に使える主成分がありません")
    if not np.all(np.isfinite(components)):
        raise ValueError("PCA出力に非有限値が含まれています")

    order = np.argsort(timestamps, kind="stable")
    sorted_timestamps = timestamps[order]
    sorted_components = components[order]
    keep = np.concatenate(([True], np.diff(sorted_timestamps) > 0))
    duplicates_removed = int((~keep).sum())
    sorted_timestamps = sorted_timestamps[keep]
    sorted_components = sorted_components[keep]
    if sorted_timestamps.size < 4:
        raise ValueError("重複タイムスタンプを除くと有効なパケットが4件未満です")
    return sorted_components, sorted_timestamps, duplicates_removed


def _lomb_scargle(time_seconds: np.ndarray, signal: np.ndarray, angular_frequencies: np.ndarray) -> np.ndarray:
    """SciPy新旧双方でNotebook相当の正規化ピリオドグラムを計算する。"""

    kwargs: Dict[str, Any] = {"precenter": True, "normalize": True}
    try:
        values = lombscargle(time_seconds, signal, angular_frequencies, floating_mean=True, **kwargs)
    except TypeError:
        # scipy<1.15にはfloating_meanがない。PCA出力は既に中心化されているため、
        # precenter=Trueの古いAPIが最も近い互換動作になる。
        values = lombscargle(time_seconds, signal, angular_frequencies, **kwargs)
    return np.nan_to_num(np.asarray(values, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)


def quantize_periodograms(periodograms: np.ndarray) -> List[List[int]]:
    """Circom入力へ、固定形状・非負・上限付き固定小数点として変換する。"""

    if periodograms.shape != (PCA_COMPONENTS, N_FREQUENCIES):
        raise ValueError(f"periodograms は ({PCA_COMPONENTS}, {N_FREQUENCIES}) である必要があります")
    clipped = np.clip(np.nan_to_num(periodograms, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0)
    return np.rint(clipped * PERIODOGRAM_POWER_SCALE).astype(np.int64).tolist()


def run_lomb_scargle_pipeline_from_pca(
    principal_components: np.ndarray,
    timestamps_ns: np.ndarray,
    *,
    pc_explained_variance_ratio: np.ndarray | None = None,
    selected_subcarrier_indices: np.ndarray | None = None,
    selected_snr: np.ndarray | None = None,
    n_subcarriers_total: int | None = None,
) -> Dict[str, Any]:
    """既存パイプラインが生成したPCA時系列にLomb--Scargleだけを適用する。"""

    if lombscargle is None:
        raise RuntimeError("Lomb-Scargle解析に必要な scipy が未インストールです")

    started = time.perf_counter()
    components, timestamps, duplicates_removed = _sort_and_deduplicate(principal_components, timestamps_ns)
    time_seconds = (timestamps - timestamps[0]).astype(np.float64) / 1e9
    duration_seconds = float(time_seconds[-1])
    if not np.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("systemnsタイムスタンプから正の記録時間を計算できません")

    intervals = np.diff(time_seconds)
    actual_fs = float((time_seconds.size - 1) / duration_seconds)
    n_components = min(PCA_COMPONENTS, components.shape[1])
    angular_frequencies = 2 * np.pi * FREQUENCIES_HZ
    periodograms = np.zeros((PCA_COMPONENTS, N_FREQUENCIES), dtype=np.float64)
    for pc_index in range(n_components):
        periodograms[pc_index] = _lomb_scargle(time_seconds, components[:, pc_index], angular_frequencies)

    valid_indices = np.flatnonzero(NORMAL_FREQUENCY_MASK)
    target_peak_indices = np.zeros(PCA_COMPONENTS, dtype=np.int64)
    target_peak_powers = np.zeros(PCA_COMPONENTS, dtype=np.float64)
    for pc_index in range(n_components):
        local_index = int(np.argmax(periodograms[pc_index, NORMAL_FREQUENCY_MASK]))
        target_peak_indices[pc_index] = int(valid_indices[local_index])
        target_peak_powers[pc_index] = float(periodograms[pc_index, target_peak_indices[pc_index]])

    selected_pc_index = int(np.argmax(target_peak_powers[:n_components]))
    estimated_bin = int(target_peak_indices[selected_pc_index])
    global_peak_bin = int(np.argmax(periodograms[selected_pc_index]))
    mean_interval = float(np.mean(intervals))
    interval_cv = float(np.std(intervals) / mean_interval) if mean_interval > 0 else 0.0

    selected_indices = np.asarray(
        selected_subcarrier_indices if selected_subcarrier_indices is not None else [], dtype=np.int64
    ).reshape(-1)
    snr_values = np.asarray(selected_snr if selected_snr is not None else [], dtype=np.float64).reshape(-1)
    explained_variance = np.asarray(
        pc_explained_variance_ratio if pc_explained_variance_ratio is not None else [], dtype=np.float64
    ).reshape(-1)

    result = {
        "algorithm_version": "shared-pca-lomb-scargle-v1",
        "breathing_rate_bpm": float(FREQUENCIES_HZ[estimated_bin] * 60),
        "peak_freq_hz": float(FREQUENCIES_HZ[estimated_bin]),
        "peak_power": float(periodograms[selected_pc_index, estimated_bin]),
        "global_peak_bpm": float(FREQUENCIES_HZ[global_peak_bin] * 60),
        "global_peak_freq_hz": float(FREQUENCIES_HZ[global_peak_bin]),
        "selected_pc": selected_pc_index + 1,
        "pc_explained_variance_ratio": [float(v) for v in explained_variance[:n_components]],
        "pc_target_peak_powers": [float(v) for v in target_peak_powers[:n_components]],
        "selected_pc_waveform": [float(v) for v in components[:, selected_pc_index]],
        "n_samples": int(components.shape[0]),
        "n_subcarriers_total": int(n_subcarriers_total or 0),
        "n_subcarriers_selected": int(selected_indices.size),
        "selected_subcarrier_indices": [int(v) for v in selected_indices],
        "selected_snr_mean": float(np.mean(snr_values)) if snr_values.size else None,
        "duration_seconds": duration_seconds,
        "actual_sampling_rate_hz": actual_fs,
        "sampling_interval_cv": interval_cv,
        "duplicates_removed": duplicates_removed,
        "frequency_grid": {
            "min_hz": FREQ_MIN_HZ,
            "max_hz": FREQ_MAX_HZ,
            "points": N_FREQUENCIES,
        },
        "bpm_range": {"min": BPM_MIN, "max": BPM_MAX},
        "processing_time_seconds": float(time.perf_counter() - started),
        "normality_rule": "selected PC global Lomb-Scargle peak is within bpm_range",
        "circom_scope": "periodogram range, PC selection, argmax, and normal BPM range",
        "certificate_input": {"powers": quantize_periodograms(periodograms)},
    }
    logger.info(
        "Lomb-Scargle completed from shared PCA: estimated=%.2f bpm, global=%.2f bpm, PC%d, %.3fs",
        result["breathing_rate_bpm"],
        result["global_peak_bpm"],
        result["selected_pc"],
        result["processing_time_seconds"],
    )
    return result


def run_lomb_scargle_pipeline(pipeline_input: Mapping[str, Any]) -> Dict[str, Any]:
    """``breathing_pipeline`` が生成した内部入力からLomb--Scargleを実行する。"""

    required = {"principal_components", "timestamps_ns"}
    missing = required.difference(pipeline_input)
    if missing:
        raise ValueError(f"Lomb-Scargle入力が不足しています: {', '.join(sorted(missing))}")
    return run_lomb_scargle_pipeline_from_pca(
        pipeline_input["principal_components"],
        pipeline_input["timestamps_ns"],
        pc_explained_variance_ratio=pipeline_input.get("pc_explained_variance_ratio"),
        selected_subcarrier_indices=pipeline_input.get("selected_subcarrier_indices"),
        selected_snr=pipeline_input.get("selected_snr"),
        n_subcarriers_total=pipeline_input.get("n_subcarriers_total"),
    )
