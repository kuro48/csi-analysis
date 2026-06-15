"""
CSI変換結果可視化サービス

FFT・ウェーブレット・MUSIC変換後の周波数行列をmatplotlibでグラフ化し、
ZKPに入力する前の状態をPNGファイルとして保存する。
"""

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = Path("/app/outputs/graphs")
_FALLBACK_OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs" / "graphs"

NORMAL_LOW_HZ = 0.10
NORMAL_HIGH_HZ = 0.50
ZKP_FREQ_POINTS = 31
ZKP_FREQ_START = 0.0
ZKP_FREQ_STEP = 0.02


def _resolve_output_dir(output_dir: Optional[Path]) -> Path:
    if output_dir is not None:
        return output_dir
    if _DEFAULT_OUTPUT_DIR.parent.exists():
        return _DEFAULT_OUTPUT_DIR
    return _FALLBACK_OUTPUT_DIR


def _freq_axis(num_points: Optional[int] = None) -> List[float]:
    n = num_points if num_points is not None else ZKP_FREQ_POINTS
    return [round(ZKP_FREQ_START + i * ZKP_FREQ_STEP, 3) for i in range(n)]


def save_fft_graph(
    fft_matrix: List[List[int]],
    csi_data_id: str,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    FFT変換後の周波数行列をヒートマップ+平均スペクトルとして保存する。

    Args:
        fft_matrix: ZKP入力行列 [NUM_FREQ_POINTS][NUM_SUBCARRIERS]（整数スケール済み）
        csi_data_id: CSIデータID（保存先サブディレクトリ名に使用）
        output_dir: 保存先ルートディレクトリ（省略時はデフォルト）

    Returns:
        保存されたPNGファイルのPath、失敗時はNone
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        save_dir = _resolve_output_dir(output_dir) / str(csi_data_id)
        save_dir.mkdir(parents=True, exist_ok=True)
        out_path = save_dir / "fft.png"

        matrix = np.array(fft_matrix, dtype=np.float64)
        num_freq_points = matrix.shape[0] if matrix.ndim == 2 else ZKP_FREQ_POINTS
        freqs = _freq_axis(num_freq_points)
        num_subcarriers = matrix.shape[1] if matrix.ndim == 2 else 0

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        fig.suptitle(f"FFT Spectrum (ZKP Input) — {csi_data_id}", fontsize=12)

        ax0 = axes[0]
        im = ax0.imshow(
            matrix,
            aspect="auto",
            origin="lower",
            cmap="viridis",
            extent=[0, num_subcarriers, freqs[0], freqs[-1]],
        )
        ax0.set_xlabel("Subcarrier index")
        ax0.set_ylabel("Frequency (Hz)")
        ax0.set_title("Heatmap: freq × subcarrier")
        ax0.axhline(NORMAL_LOW_HZ, color="red", linestyle="--", linewidth=0.8, label=f"{NORMAL_LOW_HZ} Hz")
        ax0.axhline(NORMAL_HIGH_HZ, color="orange", linestyle="--", linewidth=0.8, label=f"{NORMAL_HIGH_HZ} Hz")
        ax0.legend(fontsize=8)
        fig.colorbar(im, ax=ax0, label="Amplitude (scaled)")

        ax1 = axes[1]
        mean_spec = matrix.mean(axis=1)
        ax1.plot(freqs, mean_spec, color="steelblue", linewidth=1.2)
        ax1.axvspan(NORMAL_LOW_HZ, NORMAL_HIGH_HZ, alpha=0.15, color="green", label="Normal range")
        ax1.set_xlabel("Frequency (Hz)")
        ax1.set_ylabel("Mean amplitude (scaled)")
        ax1.set_title("Mean spectrum across subcarriers")
        ax1.legend(fontsize=8)

        fig.tight_layout()
        fig.savefig(out_path, dpi=120, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"FFT graph saved: {out_path}")
        return out_path

    except Exception as exc:
        logger.error(f"Failed to save FFT graph: {exc}", exc_info=True)
        return None


def save_wavelet_graph(
    wavelet_matrix: List[List[int]],
    csi_data_id: str,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    ウェーブレット変換後の周波数行列（線形再ビン化済み）をヒートマップとして保存する。

    Args:
        wavelet_matrix: ZKP入力行列 [NUM_FREQ_POINTS][NUM_SUBCARRIERS]（整数スケール済み）
        csi_data_id: CSIデータID
        output_dir: 保存先ルートディレクトリ

    Returns:
        保存されたPNGファイルのPath、失敗時はNone
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        save_dir = _resolve_output_dir(output_dir) / str(csi_data_id)
        save_dir.mkdir(parents=True, exist_ok=True)
        out_path = save_dir / "wavelet.png"

        matrix = np.array(wavelet_matrix, dtype=np.float64)
        num_freq_points = matrix.shape[0] if matrix.ndim == 2 else ZKP_FREQ_POINTS
        freqs = _freq_axis(num_freq_points)
        num_subcarriers = matrix.shape[1] if matrix.ndim == 2 else 0

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        fig.suptitle(f"Wavelet Spectrum (ZKP Input, linear-rebinned) — {csi_data_id}", fontsize=12)

        ax0 = axes[0]
        im = ax0.imshow(
            matrix,
            aspect="auto",
            origin="lower",
            cmap="plasma",
            extent=[0, num_subcarriers, freqs[0], freqs[-1]],
        )
        ax0.set_xlabel("Subcarrier index")
        ax0.set_ylabel("Frequency (Hz)")
        ax0.set_title("Heatmap: freq × subcarrier")
        ax0.axhline(NORMAL_LOW_HZ, color="red", linestyle="--", linewidth=0.8, label=f"{NORMAL_LOW_HZ} Hz")
        ax0.axhline(NORMAL_HIGH_HZ, color="orange", linestyle="--", linewidth=0.8, label=f"{NORMAL_HIGH_HZ} Hz")
        ax0.legend(fontsize=8)
        fig.colorbar(im, ax=ax0, label="Amplitude (scaled)")

        ax1 = axes[1]
        mean_spec = matrix.mean(axis=1)
        ax1.plot(freqs, mean_spec, color="darkorchid", linewidth=1.2)
        ax1.axvspan(NORMAL_LOW_HZ, NORMAL_HIGH_HZ, alpha=0.15, color="green", label="Normal range")
        ax1.set_xlabel("Frequency (Hz)")
        ax1.set_ylabel("Mean amplitude (scaled)")
        ax1.set_title("Mean spectrum across subcarriers")
        ax1.legend(fontsize=8)

        fig.tight_layout()
        fig.savefig(out_path, dpi=120, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"Wavelet graph saved: {out_path}")
        return out_path

    except Exception as exc:
        logger.error(f"Failed to save wavelet graph: {exc}", exc_info=True)
        return None


def save_music_graph(
    music_matrix: List[List[int]],
    csi_data_id: str,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    MUSIC擬似スペクトル（log圧縮+正規化済み）をヒートマップとして保存する。

    Args:
        music_matrix: ZKP入力行列 [NUM_FREQ_POINTS][NUM_SUBCARRIERS]（整数スケール済み）
        csi_data_id: CSIデータID
        output_dir: 保存先ルートディレクトリ

    Returns:
        保存されたPNGファイルのPath、失敗時はNone
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        save_dir = _resolve_output_dir(output_dir) / str(csi_data_id)
        save_dir.mkdir(parents=True, exist_ok=True)
        out_path = save_dir / "music.png"

        matrix = np.array(music_matrix, dtype=np.float64)
        num_freq_points = matrix.shape[0] if matrix.ndim == 2 else ZKP_FREQ_POINTS
        freqs = _freq_axis(num_freq_points)
        num_subcarriers = matrix.shape[1] if matrix.ndim == 2 else 0

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        fig.suptitle(f"MUSIC Pseudo-spectrum (ZKP Input, log-compressed) — {csi_data_id}", fontsize=12)

        ax0 = axes[0]
        im = ax0.imshow(
            matrix,
            aspect="auto",
            origin="lower",
            cmap="inferno",
            extent=[0, num_subcarriers, freqs[0], freqs[-1]],
        )
        ax0.set_xlabel("Subcarrier index")
        ax0.set_ylabel("Frequency (Hz)")
        ax0.set_title("Heatmap: freq × subcarrier")
        ax0.axhline(NORMAL_LOW_HZ, color="cyan", linestyle="--", linewidth=0.8, label=f"{NORMAL_LOW_HZ} Hz")
        ax0.axhline(NORMAL_HIGH_HZ, color="yellow", linestyle="--", linewidth=0.8, label=f"{NORMAL_HIGH_HZ} Hz")
        ax0.legend(fontsize=8)
        fig.colorbar(im, ax=ax0, label="Normalized pseudo-spectrum (scaled)")

        ax1 = axes[1]
        mean_spec = matrix.mean(axis=1)
        ax1.plot(freqs, mean_spec, color="crimson", linewidth=1.2)
        ax1.axvspan(NORMAL_LOW_HZ, NORMAL_HIGH_HZ, alpha=0.15, color="green", label="Normal range")
        ax1.set_xlabel("Frequency (Hz)")
        ax1.set_ylabel("Mean pseudo-spectrum (scaled)")
        ax1.set_title("Mean spectrum across subcarriers")
        ax1.legend(fontsize=8)

        fig.tight_layout()
        fig.savefig(out_path, dpi=120, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"MUSIC graph saved: {out_path}")
        return out_path

    except Exception as exc:
        logger.error(f"Failed to save MUSIC graph: {exc}", exc_info=True)
        return None


def save_combined_graph(
    fft_matrix: List[List[int]],
    wavelet_matrix: List[List[int]],
    music_matrix: List[List[int]],
    csi_data_id: str,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    FFT・ウェーブレット・MUSICの3手法を縦に並べた比較グラフを
    PNG・SVG・PDF の3形式で保存する。

    Returns:
        保存された PNG ファイルの Path（代表）、失敗時は None
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec

        save_dir = _resolve_output_dir(output_dir) / str(csi_data_id)
        save_dir.mkdir(parents=True, exist_ok=True)

        datasets = []
        if fft_matrix:
            datasets.append(("FFT", np.array(fft_matrix, dtype=np.float64), "viridis", "steelblue"))
        if wavelet_matrix:
            datasets.append(("Wavelet", np.array(wavelet_matrix, dtype=np.float64), "plasma", "darkorchid"))
        if music_matrix:
            datasets.append(("MUSIC", np.array(music_matrix, dtype=np.float64), "inferno", "crimson"))

        if not datasets:
            logger.warning("No matrix data available for combined graph")
            return None

        n_methods = len(datasets)
        fig = plt.figure(figsize=(14, 5 * n_methods))
        fig.suptitle(f"CSI Spectrum Comparison — {csi_data_id}", fontsize=13, y=1.01)
        gs = GridSpec(n_methods, 2, figure=fig, hspace=0.45, wspace=0.3)

        for row, (label, matrix, cmap, line_color) in enumerate(datasets):
            num_freq_points = matrix.shape[0]
            freqs = _freq_axis(num_freq_points)
            num_subcarriers = matrix.shape[1] if matrix.ndim == 2 else 0
            mean_spec = matrix.mean(axis=1)

            # ヒートマップ
            ax_heat = fig.add_subplot(gs[row, 0])
            im = ax_heat.imshow(
                matrix, aspect="auto", origin="lower", cmap=cmap,
                extent=[0, num_subcarriers, freqs[0], freqs[-1]],
            )
            ax_heat.set_xlabel("Subcarrier index")
            ax_heat.set_ylabel("Frequency (Hz)")
            ax_heat.set_title(f"{label} — Heatmap")
            ax_heat.axhline(NORMAL_LOW_HZ, color="red", linestyle="--", linewidth=0.8, label=f"{NORMAL_LOW_HZ} Hz")
            ax_heat.axhline(NORMAL_HIGH_HZ, color="orange", linestyle="--", linewidth=0.8, label=f"{NORMAL_HIGH_HZ} Hz")
            ax_heat.legend(fontsize=7)
            fig.colorbar(im, ax=ax_heat, label="Amplitude (scaled)")

            # 平均スペクトル
            ax_spec = fig.add_subplot(gs[row, 1])
            ax_spec.plot(freqs, mean_spec, color=line_color, linewidth=1.2)
            ax_spec.axvspan(NORMAL_LOW_HZ, NORMAL_HIGH_HZ, alpha=0.15, color="green", label="Normal range")
            ax_spec.set_xlabel("Frequency (Hz)")
            ax_spec.set_ylabel("Mean amplitude (scaled)")
            ax_spec.set_title(f"{label} — Mean spectrum")
            ax_spec.legend(fontsize=7)

        png_path = save_dir / "combined.png"
        svg_path = save_dir / "combined.svg"
        pdf_path = save_dir / "combined.pdf"

        fig.savefig(png_path, dpi=120, bbox_inches="tight")
        fig.savefig(svg_path, bbox_inches="tight")
        fig.savefig(pdf_path, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"Combined graph saved: {png_path} / .svg / .pdf")
        return png_path

    except Exception as exc:
        logger.error(f"Failed to save combined graph: {exc}", exc_info=True)
        return None
