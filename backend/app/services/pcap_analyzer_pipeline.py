"""
PCAPAnalyzer の CSI 読み込みと解析パイプライン。
"""

from pathlib import Path
import shlex
import subprocess
import tempfile
from typing import Any, Dict

from CSIKit.reader import get_reader
from CSIKit.util import csitools
import numpy as np
import pandas as pd

from app.core.config import settings
from app.services.pcap_analyzer_common import _build_empty_analysis_result


def _select_picoscenes_subcarriers(
    self,
    subcarrier_indices: np.ndarray,
    max_subcarriers: int = 245,
) -> np.ndarray:
    """PicoScenes の高密度トーンから既存パイプライン向けにサブキャリアを間引く。"""
    if subcarrier_indices.size <= max_subcarriers:
        return np.arange(subcarrier_indices.size)

    non_zero_positions = np.where(subcarrier_indices != 0)[0]
    if non_zero_positions.size >= max_subcarriers:
        ranked = non_zero_positions[np.argsort(np.abs(subcarrier_indices[non_zero_positions]))[:max_subcarriers]]
    else:
        ranked = np.argsort(np.abs(subcarrier_indices))[:max_subcarriers]

    return np.sort(ranked)


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
    """PicoScenes for Python Toolbox で .csi を DataFrame に変換する。"""
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

    selected_positions = self._select_picoscenes_subcarriers(subcarrier_indices)
    selected_indices = subcarrier_indices[selected_positions]

    rows = []
    fallback_ns = None
    for frame_idx, frame in enumerate(raw_frames):
        frame_csi = frame.get("CSI") or {}
        frame_rx = frame.get("RxSBasic") or {}
        mag = np.asarray(frame_csi.get("Mag", []), dtype=np.float32)
        if mag.size != num_tones * num_sts * num_rx:
            self.logger.debug(
                "Skipping PicoScenes frame %s due to unexpected Mag size: %s",
                frame_idx,
                mag.size,
            )
            continue

        # Toolbox examples reshape CSI in Fortran order. Mag follows the same layout.
        mag_matrix = mag.reshape((num_tones, num_sts, num_rx), order="F")
        tone_vector = mag_matrix[:, 0, 0]

        system_ns = frame_rx.get("systemns")
        if system_ns is None:
            if fallback_ns is None:
                fallback_ns = 0
            else:
                fallback_ns += int(self.DOWNSAMPLE_INTERVAL_S * 1_000_000_000)
            system_ns = fallback_ns

        row = {"timestamp": pd.to_datetime(int(system_ns), unit="ns", errors="coerce")}
        for pos, subcarrier_index in zip(selected_positions, selected_indices):
            row[str(int(subcarrier_index))] = float(tone_vector[pos])
        rows.append(row)

    if not rows:
        raise ValueError("No valid PicoScenes frames could be converted")

    df = pd.DataFrame(rows)
    self.logger.info(
        "PicoScenes DataFrame作成完了: frames=%s, selected_subcarriers=%s, original_tones=%s, cbw=%s",
        len(df),
        len(selected_indices),
        num_tones,
        rx_info.get("CBW"),
    )
    return df


def _matlab_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# --- OLD: PicoScenes .csi を MATLAB Toolbox で CSV 化する実装 ------------
# def _convert_picoscenes_to_dataframe_with_matlab(
#     self,
#     file_path: str,
# ) -> pd.DataFrame:
#     """PicoScenes MATLAB Toolbox で .csi を CSV 化し、DataFrame に変換する。"""
#     helper_dir = Path(__file__).resolve().parent / "matlab"
#     helper_path = helper_dir / "convert_picoscenes_to_csv.m"
#     if not helper_path.exists():
#         raise RuntimeError(f"MATLAB PicoScenes converter is missing: {helper_path}")
#
#     with tempfile.TemporaryDirectory() as temp_dir:
#         output_csv = str(Path(temp_dir) / "picoscenes.csv")
#         addpath_commands = [f"addpath({_matlab_quote(str(helper_dir))})"]
#         if settings.PICOSCENES_MATLAB_TOOLBOX_PATH:
#             addpath_commands.insert(
#                 0,
#                 "addpath(genpath("
#                 f"{_matlab_quote(settings.PICOSCENES_MATLAB_TOOLBOX_PATH)}"
#                 "))",
#             )
#
#         batch_command = "; ".join(
#             addpath_commands
#             + [
#                 "convert_picoscenes_to_csv("
#                 f"{_matlab_quote(str(Path(file_path).resolve()))}, "
#                 f"{_matlab_quote(output_csv)}, "
#                 "245"
#                 ")"
#             ]
#         )
#         command = shlex.split(settings.MATLAB_COMMAND) + ["-batch", batch_command]
#
#         self.logger.info(
#             "PicoScenes MATLAB変換開始: file=%s, command=%s",
#             file_path,
#             settings.MATLAB_COMMAND,
#         )
#         try:
#             completed = subprocess.run(
#                 command,
#                 check=True,
#                 capture_output=True,
#                 text=True,
#                 timeout=settings.PICOSCENES_MATLAB_TIMEOUT_SECONDS,
#             )
#         except FileNotFoundError as exc:
#             raise RuntimeError(
#                 "MATLAB command was not found. Set MATLAB_COMMAND or use "
#                 "PICOSCENES_PARSER=python to use the Python toolbox."
#             ) from exc
#         except subprocess.TimeoutExpired as exc:
#             raise RuntimeError(
#                 "PicoScenes MATLAB parsing timed out after "
#                 f"{settings.PICOSCENES_MATLAB_TIMEOUT_SECONDS} seconds"
#             ) from exc
#         except subprocess.CalledProcessError as exc:
#             stderr = (exc.stderr or "").strip()
#             stdout = (exc.stdout or "").strip()
#             detail = stderr or stdout or str(exc)
#             raise RuntimeError(f"PicoScenes MATLAB parsing failed: {detail[-2000:]}") from exc
#
#         if completed.stderr:
#             self.logger.debug("PicoScenes MATLAB stderr: %s", completed.stderr.strip())
#
#         df = pd.read_csv(output_csv)
#
#     if df.empty:
#         raise ValueError("PicoScenes MATLAB parser returned no frames")
#     if "timestamp" not in df.columns:
#         raise ValueError("PicoScenes MATLAB parser output is missing timestamp column")
#
#     df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", errors="coerce")
#     for col in df.columns:
#         if col == "timestamp":
#             continue
#         df[col] = pd.to_numeric(df[col], errors="coerce")
#
#     self.logger.info(
#         "PicoScenes MATLAB DataFrame作成完了: frames=%s, selected_subcarriers=%s",
#         len(df),
#         len([col for col in df.columns if col != "timestamp"]),
#     )
#     return df
# -------------------------------------------------------------------------


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
) -> Dict[str, Any]:
    """変換済み DataFrame を解析し、各手法の周波数表現と呼吸推定値を返す。"""
    empty_result = _build_empty_analysis_result(self)

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


def analyze_pcap_file(
    self,
    file_path: str,
    include_wavelet: bool = True,
    include_music: bool = True,
) -> Dict[str, Any]:
    """PCAP を解析し、各手法の周波数表現と呼吸推定値を返す。"""
    if Path(file_path).suffix.lower() == ".csi":
        raise ValueError("Use analyze_csi_file_with_picoscenes for .csi files")

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
    )


def analyze_csi_file_with_picoscenes(
    self,
    file_path: str,
    include_wavelet: bool = True,
    include_music: bool = True,
) -> Dict[str, Any]:
    """CSI ファイルを解析する。

    MATLAB パーサー選択時は .csv を受け取る。
    Python パーサー選択時は従来どおり PicoScenes .csi を受け取る。
    """
    # --- OLD: .csi 専用だった呼び出し ---
    # df = self._convert_picoscenes_to_dataframe(file_path)
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
    )
