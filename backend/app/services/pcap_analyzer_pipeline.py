"""
PCAPAnalyzer の CSI 読み込みと解析パイプライン。
"""

from pathlib import Path
import shlex
import subprocess
import tempfile
from typing import Any, Dict, Optional

from CSIKit.reader import get_reader
from CSIKit.util import csitools
import numpy as np
import pandas as pd

from app.core.config import settings
from app.services.pcap_analyzer_common import (
    _build_empty_analysis_result,
    _detect_band,
    extract_phase_dataframe,
)


def _resample_to_target_rate(
    self,
    df: pd.DataFrame,
    target_interval_s: float = 0.01,
) -> pd.DataFrame:
    """実サンプリングレートが目標より高い場合、ダウンサンプリングする。"""
    if "timestamp" not in df.columns or len(df) < 2:
        return df

    ts = pd.to_datetime(df["timestamp"])
    duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
    if duration_s <= 0:
        return df

    actual_fs = (len(df) - 1) / duration_s
    target_fs = 1.0 / target_interval_s

    if actual_fs <= target_fs * 1.1:
        return df

    attrs = df.attrs.copy()
    data_cols = [col for col in df.columns if col != "timestamp"]
    rule = f"{int(target_interval_s * 1000)}ms"

    resampled = (
        df.set_index("timestamp")[data_cols]
        .resample(rule)
        .mean()
        .dropna(how="all")
        .reset_index()
    )
    resampled.attrs = attrs

    self.logger.info(
        "ダウンサンプリング: %.1f Hz → %.1f Hz (%d → %d フレーム)",
        actual_fs,
        target_fs,
        len(df),
        len(resampled),
    )
    return resampled


def _compute_signal_series(df: pd.DataFrame, max_points: int = 500) -> Optional[Dict[str, Any]]:
    """サブキャリア平均振幅の時系列データを返す（最大 max_points 点）。"""
    data_cols = [col for col in df.columns if col.lstrip("-").isdigit()]
    if not data_cols or df.empty:
        return None

    amplitude_avg = df[data_cols].mean(axis=1).values.astype(float)

    start_timestamp: Optional[str] = None
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"])
        time_s = (ts - ts.iloc[0]).dt.total_seconds().values.astype(float)
        first_ts = ts.iloc[0]
        if not pd.isnull(first_ts):
            start_timestamp = first_ts.isoformat()
    else:
        time_s = np.arange(len(df), dtype=float) * 0.01

    n = len(amplitude_avg)
    if n > max_points:
        indices = np.linspace(0, n - 1, max_points, dtype=int)
        amplitude_avg = amplitude_avg[indices]
        time_s = time_s[indices]

    return {
        "start_timestamp": start_timestamp,
        "time": {str(i): float(t) for i, t in enumerate(time_s)},
        "amplitude_avg": {
            str(i): float(a) if np.isfinite(a) else None
            for i, a in enumerate(amplitude_avg)
        },
    }


def _convert_picoscenes_to_dataframe(
    self,
    file_path: str,
) -> pd.DataFrame:
    """.csv は MATLAB を介さず pandas で直接読み込む。.csi はパーサー設定に従う。"""
    if Path(file_path).suffix.lower() == ".csv":
        return self._read_csv_directly(file_path)

    parser = settings.PICOSCENES_PARSER.lower()
    if parser == "matlab":
        return self._convert_csv_to_dataframe_with_matlab(file_path)
    if parser == "python":
        return self._convert_picoscenes_to_dataframe_with_python(file_path)
    raise ValueError(f"Unsupported PICOSCENES_PARSER: {settings.PICOSCENES_PARSER}")


def _read_csv_directly(
    self,
    file_path: str,
) -> pd.DataFrame:
    """CSVファイルを pandas で直接読み込んで DataFrame に変換する。

    期待するフォーマット:
      - 'timestamp' 列: ナノ秒単位の整数
      - その他の列: サブキャリアインデックス（整数）をカラム名とする振幅値
    """
    df = pd.read_csv(file_path)

    if "timestamp" not in df.columns:
        raise ValueError("CSV に 'timestamp' 列がありません")

    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", errors="coerce")
    for col in df.columns:
        if col == "timestamp":
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")

    self.logger.info(
        "CSV直接読み込み完了: frames=%s, subcarriers=%s",
        len(df),
        len([c for c in df.columns if c != "timestamp"]),
    )
    return df


def _convert_picoscenes_to_dataframe_with_python(
    self,
    file_path: str,
) -> pd.DataFrame:
    """PicoScenes for Python Toolbox で .csi を DataFrame に変換する。

    振幅・位相の両方を抽出し、サブキャリアインデックスの最大絶対値から
    帯域幅を自動検出して df.attrs["bandwidth_mhz"] に格納する。
    RxSBasic.centerFreq からバンド（"5GHz"/"6GHz"）を検出して df.attrs["band"] に格納する。
    """
    try:
        from picoscenes import Picoscenes
    except ImportError as exc:
        raise RuntimeError(
            "PicoScenes for Python Toolbox is not installed. "
            "Please install the 'picoscenes' package before parsing .csi files."
        ) from exc

    frames = Picoscenes(file_path)
    raw_frames = getattr(frames, "raw", None)
    if not raw_frames:
        raise ValueError("PicoScenes file contains no frames")

    first_frame = raw_frames[0]
    csi_info = first_frame.get("CSI") or {}
    rx_info = first_frame.get("RxSBasic") or {}

    num_tones = int(csi_info.get("numTones", 0))
    num_sts = int(rx_info.get("numSTS", 1) or 1)
    num_rx = int(rx_info.get("numRx", csi_info.get("numRx", 1)) or 1)
    subcarrier_indices = np.asarray(csi_info.get("SubcarrierIndex", []), dtype=np.int32)

    if num_tones <= 0 or subcarrier_indices.size != num_tones:
        raise ValueError("Invalid PicoScenes CSI metadata: numTones/SubcarrierIndex mismatch")

    mag_array = np.empty((len(raw_frames), num_tones), dtype=np.float32)
    phase_array = np.empty((len(raw_frames), num_tones), dtype=np.float32)
    timestamps: list = []
    valid_count = 0
    fallback_ns = None
    has_phase = False

    for frame_idx, frame in enumerate(raw_frames):
        frame_csi = frame.get("CSI") or {}
        frame_rx = frame.get("RxSBasic") or {}
        mag = np.asarray(frame_csi.get("Mag", []), dtype=np.float32)
        phase_raw = np.asarray(frame_csi.get("Phase", []), dtype=np.float32)

        if mag.size != num_tones * num_sts * num_rx:
            self.logger.debug(
                "Skipping PicoScenes frame %s due to unexpected Mag size: %s",
                frame_idx,
                mag.size,
            )
            continue

        # Toolbox examples reshape CSI in Fortran order.
        mag_matrix = mag.reshape((num_tones, num_sts, num_rx), order="F")
        tone_mag = mag_matrix[:, 0, 0]

        if phase_raw.size == num_tones * num_sts * num_rx:
            tone_phase = phase_raw.reshape((num_tones, num_sts, num_rx), order="F")[:, 0, 0]
            has_phase = True
        else:
            tone_phase = np.zeros(num_tones, dtype=np.float32)

        system_ns = frame_rx.get("systemns")
        if system_ns is None:
            if fallback_ns is None:
                fallback_ns = 0
            else:
                fallback_ns += int(self.DOWNSAMPLE_INTERVAL_S * 1_000_000_000)
            system_ns = fallback_ns

        mag_array[valid_count, :] = tone_mag
        phase_array[valid_count, :] = tone_phase
        timestamps.append(pd.to_datetime(int(system_ns), unit="ns", errors="coerce"))
        valid_count += 1

    if valid_count == 0:
        raise ValueError("No valid PicoScenes frames could be converted")

    col_names = [str(int(i)) for i in subcarrier_indices]
    phase_col_names = [f"{str(int(i))}_phase" for i in subcarrier_indices]

    df = pd.DataFrame(mag_array[:valid_count], columns=col_names)
    if has_phase:
        phase_df = pd.DataFrame(phase_array[:valid_count], columns=phase_col_names)
        df = pd.concat([df, phase_df], axis=1)
    df.insert(0, "timestamp", timestamps)

    # サブキャリアインデックスの最大絶対値から帯域幅を自動検出
    max_abs_sc = int(np.max(np.abs(subcarrier_indices))) if subcarrier_indices.size > 0 else 0
    detected_bw = 160 if max_abs_sc > 200 else 80

    # 中心周波数からバンドを検出
    center_freq_mhz = float(rx_info.get("centerFreq", 0) or 0)
    detected_band = _detect_band(center_freq_mhz)

    df.attrs["bandwidth_mhz"] = detected_bw
    df.attrs["band"] = detected_band

    self.logger.info(
        "PicoScenes DataFrame作成完了: frames=%s, subcarriers=%s, "
        "phase=%s, band=%s, bandwidth=%s MHz",
        valid_count,
        num_tones,
        has_phase,
        detected_band,
        detected_bw,
    )
    return df


def _matlab_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _convert_csv_to_dataframe_with_matlab(
    self,
    file_path: str,
) -> pd.DataFrame:
    """入力 .csv を MATLAB 経由でサブキャリア選択し、DataFrame に変換する。

    convert_picoscenes_to_csv.m が CSV を読み込み、サブキャリア選択を適用した
    うえで出力 CSV を書き出す。Python はその出力 CSV を読み込んで DataFrame を返す。
    """
    if not file_path.lower().endswith(".csv"):
        raise ValueError(
            f"MATLAB パーサーは .csv のみ受け付けます (受信: {file_path}). "
            "PICOSCENES_PARSER=python に切り替えるか、.csv ファイルを渡してください。"
        )

    helper_dir = Path(__file__).resolve().parent / "matlab"
    helper_path = helper_dir / "convert_picoscenes_to_csv.m"
    if not helper_path.exists():
        raise RuntimeError(f"MATLAB CSV converter is missing: {helper_path}")

    with tempfile.TemporaryDirectory() as temp_dir:
        output_csv = str(Path(temp_dir) / "csi_out.csv")
        addpath_commands = [f"addpath({_matlab_quote(str(helper_dir))})"]

        batch_command = "; ".join(
            addpath_commands
            + [
                "convert_picoscenes_to_csv("
                f"{_matlab_quote(str(Path(file_path).resolve()))}, "
                f"{_matlab_quote(output_csv)}, "
                "245"
                ")"
            ]
        )
        command = shlex.split(settings.MATLAB_COMMAND) + ["-batch", batch_command]

        self.logger.info(
            "CSV → MATLAB変換開始: file=%s, command=%s",
            file_path,
            settings.MATLAB_COMMAND,
        )
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=settings.PICOSCENES_MATLAB_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "MATLAB command was not found. Set MATLAB_COMMAND in settings."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "MATLAB CSV parsing timed out after "
                f"{settings.PICOSCENES_MATLAB_TIMEOUT_SECONDS} seconds"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            detail = stderr or stdout or str(exc)
            raise RuntimeError(f"MATLAB CSV parsing failed: {detail[-2000:]}") from exc

        if completed.stderr:
            self.logger.debug("MATLAB stderr: %s", completed.stderr.strip())

        df = pd.read_csv(output_csv)

    if df.empty:
        raise ValueError("MATLAB CSV parser returned no frames")
    if "timestamp" not in df.columns:
        raise ValueError("MATLAB CSV parser output is missing timestamp column")

    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", errors="coerce")
    for col in df.columns:
        if col == "timestamp":
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")

    self.logger.info(
        "MATLAB CSV DataFrame作成完了: frames=%s, selected_subcarriers=%s",
        len(df),
        len([col for col in df.columns if col != "timestamp"]),
    )
    return df


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


def _analyze_dataframe(
    self,
    df: pd.DataFrame,
    no_frames: int,
    no_subcarriers: int,
    include_wavelet: bool = True,
    include_music: bool = True,
    include_breathing: bool = True,
    background_subcarrier_medians: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """変換済み DataFrame を解析し、FFT・Wavelet・MUSIC の周波数表現と呼吸推定値を返す。"""
    empty_result = _build_empty_analysis_result(self)
    if not include_breathing:
        empty_result["breathing_rate_comparison"] = None

    df = self.drop_invalid_rows(df)
    if df.empty:
        self.logger.warning("有効なデータが存在しません")
        return empty_result

    self.logger.info(f"データクリーニング後: {len(df)}行")

    bandwidth_mhz = int(df.attrs.get("bandwidth_mhz", 80))
    band = str(df.attrs.get("band", "5GHz"))
    df = self.remove_unnecessary_subcarriers(df, band=band, bandwidth_mhz=bandwidth_mhz)
    remaining_subcarriers = len([col for col in df.columns if col.lstrip("-").isdigit()])
    subcarrier_cols = [col for col in df.columns if col.lstrip("-").isdigit()]
    subcarrier_medians = {
        col: float(np.median(df[col].values))
        for col in subcarrier_cols
    }
    if background_subcarrier_medians:
        df = df.copy()
        for col in subcarrier_cols:
            base_offset = float(background_subcarrier_medians.get(col, 0.0))
            df[col] = np.maximum(df[col].values - base_offset, 0.0)
        self.logger.info(
            "背景差分除去完了: %s サブキャリア",
            len(background_subcarrier_medians),
        )

    raw_signal = _compute_signal_series(df)
    df = self.apply_bandpass_filter(df, self.DOWNSAMPLE_INTERVAL_S)
    filtered_signal = _compute_signal_series(df)

    # バンドパス後(最高0.5 Hz)は5 Hzで情報完全保存 → Wavelet/MUSIC前にダウンサンプル
    df_wavelet = self._resample_to_target_rate(df, target_interval_s=self.WAVELET_DOWNSAMPLE_INTERVAL_S)

    fft_df = self.apply_fourier_transform(df, self.DOWNSAMPLE_INTERVAL_S)
    if fft_df.empty:
        self.logger.warning("FFT結果が空です")
        empty_result["subcarrier_medians"] = subcarrier_medians
        return empty_result

    fft_df = fft_df[
        (fft_df["frequency"] >= self.BREATHING_MIN_FREQ)
        & (fft_df["frequency"] <= self.BREATHING_MAX_FREQ)
    ].reset_index(drop=True)

    bins = self.make_bins(self.BREATHING_MAX_FREQ, self.FREQUENCY_BIN_STEP)
    binned_fft_df = self.average_magnitude_by_frequency_bins(fft_df, bins)
    breathing_rate_fft = (
        self.estimate_breathing_rate(fft_df, freq_col="frequency")
        if include_breathing
        else None
    )

    wavelet_df = self.apply_wavelet_transform(df_wavelet, self.WAVELET_DOWNSAMPLE_INTERVAL_S) if include_wavelet else pd.DataFrame()
    music_df = self.apply_music_transform(df_wavelet, self.WAVELET_DOWNSAMPLE_INTERVAL_S) if include_music else pd.DataFrame()

    binned_wavelet_df = pd.DataFrame()
    binned_music_df = pd.DataFrame()
    breathing_rate_wavelet = None
    breathing_rate_music = None

    if not wavelet_df.empty:
        wavelet_df = wavelet_df[
            (wavelet_df["frequency"] >= self.BREATHING_MIN_FREQ)
            & (wavelet_df["frequency"] <= self.BREATHING_MAX_FREQ)
        ].reset_index(drop=True)
        binned_wavelet_df = self.average_magnitude_by_frequency_bins(wavelet_df, bins)
        if include_breathing:
            breathing_rate_wavelet = self.estimate_breathing_rate(wavelet_df, freq_col="frequency")

    if not music_df.empty:
        music_df = music_df[
            (music_df["frequency"] >= self.BREATHING_MIN_FREQ)
            & (music_df["frequency"] <= self.BREATHING_MAX_FREQ)
        ].reset_index(drop=True)
        binned_music_df = self.average_magnitude_by_frequency_bins(music_df, bins)
        if include_breathing:
            breathing_rate_music = self.estimate_breathing_rate(music_df, freq_col="frequency")

    breathing_rate_comparison = (
        self.compare_breathing_rate_methods({
            "fft": breathing_rate_fft,
            "wavelet": breathing_rate_wavelet,
            "music": breathing_rate_music,
        })
        if include_breathing
        else None
    )

    # --- 位相パイプライン (振幅と並列に実行) ---
    phase_df = extract_phase_dataframe(df)
    has_phase = not phase_df.empty
    binned_fft_phase_df = pd.DataFrame()
    binned_wavelet_phase_df = pd.DataFrame()
    binned_music_phase_df = pd.DataFrame()
    breathing_rate_fft_phase = None
    breathing_rate_wavelet_phase = None
    breathing_rate_music_phase = None
    breathing_rate_phase_comparison = None

    if has_phase:
        fft_phase_df = self.apply_fourier_transform(phase_df, self.DOWNSAMPLE_INTERVAL_S)
        if not fft_phase_df.empty:
            binned_fft_phase_df = self.average_magnitude_by_frequency_bins(fft_phase_df, bins)
            if include_breathing:
                breathing_rate_fft_phase = self.estimate_breathing_rate(
                    fft_phase_df, freq_col="frequency"
                )

        phase_df_wavelet = self._resample_to_target_rate(
            phase_df, target_interval_s=self.WAVELET_DOWNSAMPLE_INTERVAL_S
        )
        wavelet_phase_df = (
            self.apply_wavelet_transform(phase_df_wavelet, self.WAVELET_DOWNSAMPLE_INTERVAL_S)
            if include_wavelet
            else pd.DataFrame()
        )
        if not wavelet_phase_df.empty:
            binned_wavelet_phase_df = self.average_magnitude_by_frequency_bins(
                wavelet_phase_df, bins
            )
            if include_breathing:
                breathing_rate_wavelet_phase = self.estimate_breathing_rate(
                    wavelet_phase_df, freq_col="frequency"
                )

        music_phase_df = (
            self.apply_music_transform(phase_df_wavelet, self.WAVELET_DOWNSAMPLE_INTERVAL_S)
            if include_music
            else pd.DataFrame()
        )
        if not music_phase_df.empty:
            binned_music_phase_df = self.average_magnitude_by_frequency_bins(
                music_phase_df, bins
            )
            if include_breathing:
                breathing_rate_music_phase = self.estimate_breathing_rate(
                    music_phase_df, freq_col="frequency"
                )

        breathing_rate_phase_comparison = (
            self.compare_breathing_rate_methods({
                "fft": breathing_rate_fft_phase,
                "wavelet": breathing_rate_wavelet_phase,
                "music": breathing_rate_music_phase,
            })
            if include_breathing
            else None
        )

    br_info = (
        f"FFT={breathing_rate_fft:.1f}bpm" if breathing_rate_fft else "FFT=N/A",
        f"Wavelet={breathing_rate_wavelet:.1f}bpm" if breathing_rate_wavelet else "Wavelet=N/A",
        f"MUSIC={breathing_rate_music:.1f}bpm" if breathing_rate_music else "MUSIC=N/A",
    )
    br_phase_info = (
        f"FFT={breathing_rate_fft_phase:.1f}bpm" if breathing_rate_fft_phase else "FFT=N/A",
        f"Wavelet={breathing_rate_wavelet_phase:.1f}bpm" if breathing_rate_wavelet_phase else "Wavelet=N/A",
        f"MUSIC={breathing_rate_music_phase:.1f}bpm" if breathing_rate_music_phase else "MUSIC=N/A",
    )
    self.logger.info(
        f"解析完了 - フレーム数: {no_frames}, "
        f"サブキャリア: {no_subcarriers} → {remaining_subcarriers}, "
        f"有効行: {len(df)}, "
        f"FFTビン: {len(binned_fft_df)}, "
        f"Waveletビン: {len(binned_wavelet_df)}, "
        f"MUSICビン: {len(binned_music_df)}, "
        f"表示範囲: {self.BREATHING_MIN_FREQ:.2f}–{self.BREATHING_MAX_FREQ:.2f}Hz, "
        f"位相解析: {'有効' if has_phase else '位相データなし'}, "
        f"呼吸推定 振幅[{', '.join(br_info)}] "
        f"位相[{', '.join(br_phase_info)}]"
    )

    return {
        "fft": binned_fft_df,
        "wavelet": binned_wavelet_df,
        "music": binned_music_df,
        "breathing_rate_fft_bpm": breathing_rate_fft,
        "breathing_rate_wavelet_bpm": breathing_rate_wavelet,
        "breathing_rate_music_bpm": breathing_rate_music,
        "breathing_rate_comparison": breathing_rate_comparison,
        "subcarrier_medians": subcarrier_medians,
        "fft_phase": binned_fft_phase_df,
        "wavelet_phase": binned_wavelet_phase_df,
        "music_phase": binned_music_phase_df,
        "breathing_rate_fft_phase_bpm": breathing_rate_fft_phase,
        "breathing_rate_wavelet_phase_bpm": breathing_rate_wavelet_phase,
        "breathing_rate_music_phase_bpm": breathing_rate_music_phase,
        "breathing_rate_phase_comparison": breathing_rate_phase_comparison,
        "raw_signal": raw_signal,
        "filtered_signal": filtered_signal,
    }


_PCAP_EXTENSIONS = frozenset({".pcap", ".pcapng", ".cap"})
_PICOSCENES_EXTENSIONS = frozenset({".csi", ".csv"})
SUPPORTED_CSI_EXTENSIONS = _PCAP_EXTENSIONS | _PICOSCENES_EXTENSIONS

_PACKET_FORMAT_NAMES = {
    0: "NonHT",
    1: "HT",
    2: "VHT",
    3: "HE-SU",
    4: "HE-MU",
    5: "HE-TB",
    6: "EHT-SU",
}


def parse_picoscenes_metadata(
    self,
    file_path: str,
) -> Dict[str, Any]:
    """PicoScenes .csi ファイルからタイムスタンプと信号メタデータを抽出する。

    Returns:
        {
            "num_frames": int,
            "timestamps": list[str],          # ISO 8601, フレームごと
            "duration_seconds": float,
            "signal": {                        # ファイル全体のサマリー
                "center_freq_mhz": float,
                "band": str,
                "bandwidth_mhz": int,
                "packet_format": str,
                "num_rx": int,
                "num_sts": int,
            },
            "per_frame": list[dict],           # フレームごとの詳細
        }
    """
    try:
        from picoscenes import Picoscenes
    except ImportError as exc:
        raise RuntimeError(
            "PicoScenes for Python Toolbox is not installed."
        ) from exc

    frames = Picoscenes(file_path)
    raw_frames = getattr(frames, "raw", None)
    if not raw_frames:
        raise ValueError("PicoScenes file contains no frames")

    per_frame: list = []
    fallback_ns: Optional[int] = None

    for frame_idx, frame in enumerate(raw_frames):
        rx = frame.get("RxSBasic") or {}

        system_ns = rx.get("systemns")
        if system_ns is None:
            if fallback_ns is None:
                fallback_ns = 0
            else:
                fallback_ns += int(self.DOWNSAMPLE_INTERVAL_S * 1_000_000_000)
            system_ns = fallback_ns

        ts = pd.to_datetime(int(system_ns), unit="ns", errors="coerce")

        center_freq = float(rx.get("centerFreq", 0) or 0)
        cbw = int(rx.get("cbw", 0) or 0)
        pkt_fmt_raw = rx.get("packetFormat")
        pkt_fmt = _PACKET_FORMAT_NAMES.get(int(pkt_fmt_raw), str(pkt_fmt_raw)) if pkt_fmt_raw is not None else "Unknown"
        rssi_raw = rx.get("rssi")
        rssi = float(rssi_raw) if rssi_raw is not None else None
        noise_floor_raw = rx.get("noiseFloor")
        noise_floor = float(noise_floor_raw) if noise_floor_raw is not None else None
        num_rx = int(rx.get("numRx", 0) or 0)
        num_sts = int(rx.get("numSTS", 0) or 0)

        per_frame.append({
            "frame_index": frame_idx,
            "timestamp": ts.isoformat() if not pd.isnull(ts) else None,
            "timestamp_ns": int(system_ns),
            "center_freq_mhz": center_freq,
            "bandwidth_mhz": cbw,
            "packet_format": pkt_fmt,
            "rssi_dbm": rssi,
            "noise_floor_dbm": noise_floor,
            "num_rx": num_rx,
            "num_sts": num_sts,
        })

    if not per_frame:
        raise ValueError("No frames found in PicoScenes file")

    first = per_frame[0]
    ts_list = [f["timestamp"] for f in per_frame]

    valid_ns = [f["timestamp_ns"] for f in per_frame if f["timestamp_ns"] is not None]
    duration_s = (max(valid_ns) - min(valid_ns)) / 1e9 if len(valid_ns) >= 2 else 0.0

    rssi_vals = [f["rssi_dbm"] for f in per_frame if f["rssi_dbm"] is not None]
    rssi_mean = float(np.mean(rssi_vals)) if rssi_vals else None

    csi_info = (raw_frames[0].get("CSI") or {})
    sc_idx = np.asarray(csi_info.get("SubcarrierIndex", []), dtype=np.int32)
    max_abs_sc = int(np.max(np.abs(sc_idx))) if sc_idx.size > 0 else 0
    detected_bw = int(first["bandwidth_mhz"]) or (160 if max_abs_sc > 200 else 80)
    detected_band = _detect_band(first["center_freq_mhz"])

    self.logger.info(
        "PicoScenesメタデータ解析完了: frames=%s, duration=%.2fs, band=%s, bw=%sMHz, format=%s",
        len(per_frame),
        duration_s,
        detected_band,
        detected_bw,
        first["packet_format"],
    )

    return {
        "num_frames": len(per_frame),
        "timestamps": ts_list,
        "duration_seconds": duration_s,
        "signal": {
            "center_freq_mhz": first["center_freq_mhz"],
            "band": detected_band,
            "bandwidth_mhz": detected_bw,
            "packet_format": first["packet_format"],
            "num_rx": first["num_rx"],
            "num_sts": first["num_sts"],
            "rssi_mean_dbm": rssi_mean,
        },
        "per_frame": per_frame,
    }


def analyze_file(
    self,
    file_path: str,
    include_wavelet: bool = True,
    include_music: bool = True,
    include_breathing: bool = True,
    background_subcarrier_medians: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """ファイル拡張子に応じて適切なパーサーを選択し解析する。"""
    suffix = Path(file_path).suffix.lower()
    if suffix in _PCAP_EXTENSIONS:
        return analyze_pcap_file(
            self, file_path, include_wavelet, include_music,
            include_breathing, background_subcarrier_medians,
        )
    if suffix in _PICOSCENES_EXTENSIONS:
        return analyze_csi_file_with_picoscenes(
            self, file_path, include_wavelet, include_music,
            include_breathing, background_subcarrier_medians,
        )
    raise ValueError(
        f"未対応のファイル形式です: {suffix}。"
        f"対応形式: {', '.join(sorted(SUPPORTED_CSI_EXTENSIONS))}"
    )


def analyze_pcap_file(
    self,
    file_path: str,
    include_wavelet: bool = True,
    include_music: bool = True,
    include_breathing: bool = True,
    background_subcarrier_medians: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """PCAP を解析し、各手法の周波数表現と呼吸推定値を返す。"""
    reader = get_reader(file_path)
    csi_data = reader.read_file(file_path, scaled=True)
    csi_matrix, no_frames, no_subcarriers = csitools.get_CSI(csi_data)

    self.logger.info(f"CSIデータ読み込み完了: {no_frames}フレーム, {no_subcarriers}サブキャリア")
    df = self._convert_csi_to_dataframe(csi_matrix, csi_data.timestamps, no_subcarriers)
    return self._analyze_dataframe(
        df=df,
        no_frames=no_frames,
        no_subcarriers=no_subcarriers,
        include_wavelet=include_wavelet,
        include_music=include_music,
        include_breathing=include_breathing,
        background_subcarrier_medians=background_subcarrier_medians,
    )


def analyze_csi_file_with_picoscenes(
    self,
    file_path: str,
    include_wavelet: bool = True,
    include_music: bool = True,
    include_breathing: bool = True,
    background_subcarrier_medians: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """PicoScenes .csi / .csv ファイルを解析する。"""
    df = self._convert_picoscenes_to_dataframe(file_path)
    no_frames = len(df)
    no_subcarriers = len([col for col in df.columns if col.lstrip("-").isdigit()])
    self.logger.info(
        "CSIデータ読み込み完了: %sフレーム, %sサブキャリア",
        no_frames,
        no_subcarriers,
    )
    return self._analyze_dataframe(
        df=df,
        no_frames=no_frames,
        no_subcarriers=no_subcarriers,
        include_wavelet=include_wavelet,
        include_music=include_music,
        include_breathing=include_breathing,
        background_subcarrier_medians=background_subcarrier_medians,
    )
