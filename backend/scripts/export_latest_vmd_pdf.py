#!/usr/bin/env python3
"""Export the latest completed CSI record's VMD input and five modes to PDF."""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from sklearn.decomposition import PCA

from app.core.database import SessionLocal
from app.models.csi_data import CSIData
from app.services.breathing_pipeline import (
    BPM_MAX,
    BPM_MIN,
    FS,
    HIGHCUT,
    LOWCUT,
    N_SELECT,
    PCA_COMPONENTS,
    VMD_ALPHA,
    VMD_DC,
    VMD_INIT,
    VMD_K,
    VMD_TAU,
    VMD_TOL,
    bandpass_filter,
    estimate_breathing_rate_by_vmd_global_peak,
    load_csi_matrix,
    select_respiration_pc,
    select_subcarriers_by_snr,
)


def latest_completed_record() -> dict:
    db = SessionLocal()
    try:
        record = db.query(CSIData).filter(CSIData.status == "completed").order_by(CSIData.created_at.desc()).first()
        if record is None:
            raise RuntimeError("No completed CSI record was found")
        return {
            "id": str(record.id),
            "created_at": record.created_at.isoformat(),
            "file_path": record.file_path,
            "file_size": record.file_size,
            "ground_truth_bpm": record.ground_truth_bpm,
        }
    finally:
        db.close()


def analyze_vmd(file_path: str) -> dict:
    csi_matrix = load_csi_matrix(file_path)
    amplitude = np.abs(csi_matrix)
    selected_amplitude, selected_indices, _ = select_subcarriers_by_snr(
        amplitude,
        fs=FS,
        lowcut=LOWCUT,
        highcut=HIGHCUT,
        n_select=N_SELECT,
    )
    pca_input = bandpass_filter(selected_amplitude, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT, order=4)
    pca = PCA(n_components=PCA_COMPONENTS)
    principal_components = pca.fit_transform(pca_input)
    respiration_pc, best_pc_index, pc_scores = select_respiration_pc(
        principal_components,
        fs=FS,
        lowcut=LOWCUT,
        highcut=HIGHCUT,
    )
    modes, mode_infos, selected_mode = estimate_breathing_rate_by_vmd_global_peak(
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
    return {
        "input": respiration_pc,
        "modes": modes,
        "mode_infos": mode_infos,
        "selected_mode": int(selected_mode["mode_index"]),
        "selected_bpm": float(selected_mode["global_peak_bpm"]),
        "best_pc": int(best_pc_index),
        "pc_scores": pc_scores,
        "pca_variance": pca.explained_variance_ratio_,
        "selected_subcarriers": selected_indices,
        "total_subcarriers": csi_matrix.shape[1],
    }


def centered_spectrum(signal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    centered = np.asarray(signal, dtype=np.float64) - np.mean(signal)
    frequencies = np.fft.rfftfreq(centered.size, d=1 / FS)
    power = np.abs(np.fft.rfft(centered)) ** 2
    return frequencies, power


def save_pdf(record: dict, result: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    time_seconds = np.arange(len(result["input"])) / FS

    with PdfPages(output_path) as pdf:
        fig = plt.figure(figsize=(11.69, 8.27))
        grid = fig.add_gridspec(3, 1, height_ratios=[0.7, 2.2, 1.5])
        header = fig.add_subplot(grid[0])
        header.axis("off")
        truth = record["ground_truth_bpm"]
        header.text(0, 0.9, "Latest Breathing Analysis: VMD Input and Modes", fontsize=18, weight="bold")
        header.text(
            0,
            0.45,
            (
                f"Record: {record['id']}   Captured: {record['created_at']}\n"
                f"Samples: {len(result['input']):,} at {FS} Hz   Duration: {time_seconds[-1]:.2f} s   "
                f"Subcarriers: {len(result['selected_subcarriers'])}/{result['total_subcarriers']}\n"
                f"Selected PCA component: PC{result['best_pc'] + 1}   "
                f"Selected VMD mode: Mode {result['selected_mode'] + 1}   "
                f"Measured: {result['selected_bpm']:.3f} BPM   Ground truth: "
                f"{truth:.3f} BPM"
                if truth is not None
                else "not set"
            ),
            fontsize=10,
            va="top",
        )

        input_axis = fig.add_subplot(grid[1])
        input_axis.plot(time_seconds, result["input"], color="#0f766e", linewidth=0.7)
        input_axis.set_title("Representative VMD input waveform (selected respiration PCA component)")
        input_axis.set_xlabel("Time [s]")
        input_axis.set_ylabel("Amplitude")
        input_axis.grid(alpha=0.25)

        spectrum_axis = fig.add_subplot(grid[2])
        frequencies, power = centered_spectrum(result["input"])
        mask = frequencies <= 1.0
        spectrum_axis.plot(frequencies[mask] * 60, power[mask], color="#334155", linewidth=0.9)
        spectrum_axis.axvspan(BPM_MIN, BPM_MAX, color="#16a34a", alpha=0.1, label="Configured BPM range")
        spectrum_axis.set_title("VMD input spectrum")
        spectrum_axis.set_xlabel("Frequency [BPM]")
        spectrum_axis.set_ylabel("Power")
        spectrum_axis.grid(alpha=0.25)
        spectrum_axis.legend(loc="upper right")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        fig, axes = plt.subplots(VMD_K, 1, figsize=(11.69, 8.27), sharex=True)
        for index, axis in enumerate(axes):
            info = result["mode_infos"][index]
            selected = index == result["selected_mode"]
            axis.plot(
                time_seconds,
                result["modes"][index],
                color="#dc2626" if selected else "#2563eb",
                linewidth=0.65,
            )
            axis.set_ylabel(f"Mode {index + 1}")
            axis.set_title(
                f"Peak {info['global_peak_bpm']:.3f} BPM | peak ratio {info['global_peak_ratio']:.4f}"
                + (" | SELECTED" if selected else ""),
                fontsize=9,
                loc="left",
            )
            axis.grid(alpha=0.2)
        axes[-1].set_xlabel("Time [s]")
        fig.suptitle("Five VMD mode time-series", fontsize=16, weight="bold")
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        pdf.savefig(fig)
        plt.close(fig)

        fig = plt.figure(figsize=(11.69, 8.27))
        grid = fig.add_gridspec(2, 1, height_ratios=[3, 1.25])
        spectrum_axis = fig.add_subplot(grid[0])
        table_rows = []
        for index in range(VMD_K):
            frequencies, power = centered_spectrum(result["modes"][index])
            mask = frequencies <= 1.0
            selected = index == result["selected_mode"]
            spectrum_axis.plot(
                frequencies[mask] * 60,
                power[mask],
                linewidth=1.8 if selected else 0.9,
                alpha=1 if selected else 0.65,
                label=f"Mode {index + 1}" + (" (selected)" if selected else ""),
            )
            info = result["mode_infos"][index]
            table_rows.append(
                [
                    str(index + 1),
                    f"{info['global_peak_bpm']:.3f}",
                    f"{info['global_peak_ratio']:.5f}",
                    "yes" if info["is_valid"] else "no",
                    "yes" if selected else "",
                ]
            )
        spectrum_axis.axvspan(BPM_MIN, BPM_MAX, color="#16a34a", alpha=0.08)
        spectrum_axis.set_xlim(0, 60)
        spectrum_axis.set_title("Frequency spectra of all VMD modes")
        spectrum_axis.set_xlabel("Frequency [BPM]")
        spectrum_axis.set_ylabel("Power")
        spectrum_axis.grid(alpha=0.2)
        spectrum_axis.legend(ncol=3, fontsize=8)

        table_axis = fig.add_subplot(grid[1])
        table_axis.axis("off")
        table = table_axis.table(
            cellText=table_rows,
            colLabels=["Mode", "Global peak [BPM]", "Peak ratio", "In BPM range", "Selected"],
            cellLoc="center",
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.45)
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="outputs/reports")
    args = parser.parse_args()

    record = latest_completed_record()
    result = analyze_vmd(record["file_path"])
    output_path = Path(args.output_dir) / f"vmd_latest_{record['id']}.pdf"
    save_pdf(record, result, output_path)
    print(output_path.resolve())


if __name__ == "__main__":
    main()
