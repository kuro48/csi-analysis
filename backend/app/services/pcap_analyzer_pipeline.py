"""
PCAPAnalyzer の CSI 読み込みと解析パイプライン。
"""

from typing import Any, Dict

from CSIKit.reader import get_reader
from CSIKit.util import csitools
import numpy as np
import pandas as pd

from app.services.pcap_analyzer_common import _build_empty_analysis_result


def _convert_csi_to_dataframe(
    self,
    csi_matrix: np.ndarray,
    timestamps: np.ndarray,
    no_subcarriers: int,
) -> pd.DataFrame:
    """CSIKit のマトリックスを DataFrame に変換する。"""
    csi_matrix_first = csi_matrix[:, :, 0, 0]
    csi_matrix_squeezed = np.squeeze(csi_matrix_first)

    df_data = {"timestamp": pd.to_datetime(timestamps, unit="s")}
    for subcarrier_idx in range(no_subcarriers):
        df_data[str(subcarrier_idx)] = csi_matrix_squeezed[:, subcarrier_idx]

    df = pd.DataFrame(df_data)
    self.logger.info(f"DataFrame作成完了: shape={df.shape}")
    return df


def analyze_pcap_file(
    self,
    file_path: str,
    include_wavelet: bool = True,
    include_music: bool = True,
) -> Dict[str, Any]:
    """PCAP を解析し、各手法の周波数表現と呼吸推定値を返す。"""
    empty_result = _build_empty_analysis_result(self)

    reader = get_reader(file_path)
    csi_data = reader.read_file(file_path, scaled=True)
    csi_matrix, no_frames, no_subcarriers = csitools.get_CSI(csi_data)

    self.logger.info(f"CSIデータ読み込み完了: {no_frames}フレーム, {no_subcarriers}サブキャリア")

    df = self._convert_csi_to_dataframe(csi_matrix, csi_data.timestamps, no_subcarriers)
    df = self.drop_invalid_rows(df)
    if df.empty:
        self.logger.warning("有効なデータが存在しません")
        return empty_result

    self.logger.info(f"データクリーニング後: {len(df)}行")

    df = self.remove_unnecessary_subcarriers(df, channel_width="80MHz")
    remaining_subcarriers = len([col for col in df.columns if col.lstrip("-").isdigit()])

    fft_df = self.apply_fourier_transform(df, self.DOWNSAMPLE_INTERVAL_S)
    if fft_df.empty:
        self.logger.warning("FFT結果が空です")
        return empty_result

    max_freq = fft_df["frequency"].max()
    bins = self.make_bins(max_freq, self.FREQUENCY_BIN_STEP)
    binned_fft_df = self.average_magnitude_by_frequency_bins(fft_df, bins)
    breathing_rate_fft = self.estimate_breathing_rate(fft_df, freq_col="frequency")

    wavelet_df = self.apply_wavelet_transform(df, self.DOWNSAMPLE_INTERVAL_S) if include_wavelet else pd.DataFrame()
    music_df = self.apply_music_transform(df, self.DOWNSAMPLE_INTERVAL_S) if include_music else pd.DataFrame()

    binned_wavelet_df = pd.DataFrame()
    binned_music_df = pd.DataFrame()
    breathing_rate_wavelet = None
    breathing_rate_music = None

    if not wavelet_df.empty:
        binned_wavelet_df = self.average_magnitude_by_frequency_bins(wavelet_df, bins)
        breathing_rate_wavelet = self.estimate_breathing_rate(wavelet_df, freq_col="frequency")

    if not music_df.empty:
        binned_music_df = self.average_magnitude_by_frequency_bins(music_df, bins)
        breathing_rate_music = self.estimate_breathing_rate(music_df, freq_col="frequency")

    breathing_rate_comparison = self.compare_breathing_rate_methods({
        "fft": breathing_rate_fft,
        "wavelet": breathing_rate_wavelet,
        "music": breathing_rate_music,
    })

    br_info = (
        f"FFT={breathing_rate_fft:.1f}bpm" if breathing_rate_fft else "FFT=N/A",
        f"Wavelet={breathing_rate_wavelet:.1f}bpm" if breathing_rate_wavelet else "Wavelet=N/A",
        f"MUSIC={breathing_rate_music:.1f}bpm" if breathing_rate_music else "MUSIC=N/A",
    )
    self.logger.info(
        f"解析完了 - フレーム数: {no_frames}, "
        f"サブキャリア: {no_subcarriers} → {remaining_subcarriers}, "
        f"有効行: {len(df)}, "
        f"FFTビン: {len(binned_fft_df)}, "
        f"ウェーブレットビン: {len(binned_wavelet_df)}, "
        f"MUSICビン: {len(binned_music_df)}, "
        f"最大周波数: {max_freq:.2f}Hz, "
        f"呼吸推定 [{', '.join(br_info)}]"
    )

    return {
        "fft": binned_fft_df,
        "wavelet": binned_wavelet_df,
        "music": binned_music_df,
        "breathing_rate_fft_bpm": breathing_rate_fft,
        "breathing_rate_wavelet_bpm": breathing_rate_wavelet,
        "breathing_rate_music_bpm": breathing_rate_music,
        "breathing_rate_comparison": breathing_rate_comparison,
    }
