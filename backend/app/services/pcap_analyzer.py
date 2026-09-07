"""
PCAP解析サービス
Wi-Fi CSIデータをPCAPファイルから抽出し、FFTで周波数表現へ変換する。
"""

import logging

from app.services.pcap_analyzer_common import (
    average_magnitude_by_frequency_bins,
    contains_nan_or_inf,
    drop_invalid_rows,
    make_bins,
    normalize_signal,
    remove_unnecessary_subcarriers,
)
from app.services.pcap_analyzer_frequency import (
    apply_bandpass_filter,
    apply_fourier_transform,
    estimate_breathing_rate,
)
from app.services.pcap_analyzer_pipeline import (
    SUPPORTED_CSI_EXTENSIONS,
    _analyze_dataframe,
    _resample_to_target_rate,
    _convert_csi_to_dataframe,
    _convert_csv_to_dataframe_with_matlab,
    _convert_picoscenes_to_dataframe,
    _convert_picoscenes_to_dataframe_with_python,
    _read_csv_directly,
    analyze_csi_file_with_picoscenes,
    analyze_file,
    analyze_pcap_file,
    parse_picoscenes_metadata,
)
logger = logging.getLogger(__name__)


class PCAPAnalyzer:
    """PCAP解析クラス。"""

    CHANNEL_CONFIGS = {
        ("5GHz", 80): {
            "guard_bands": [(-128, -122), (122, 127)],
            "pilots": [-103, -75, -39, -11, 11, 39, 75, 103],
        },
        ("5GHz", 160): {
            "guard_bands": [(-256, -250), (250, 255)],
            "pilots": [
                -231, -203, -167, -139, -117, -89, -53, -25,
                  25,   53,   89,  117,  139, 167, 203, 231,
            ],
        },
        ("6GHz", 80): {
            "guard_bands": [(-128, -122), (122, 127)],
            "pilots": [-103, -75, -39, -11, 11, 39, 75, 103],
        },
        ("6GHz", 160): {
            "guard_bands": [(-256, -250), (250, 255)],
            "pilots": [
                -231, -203, -167, -139, -117, -89, -53, -25,
                  25,   53,   89,  117,  139, 167, 203, 231,
            ],
        },
    }

    DOWNSAMPLE_INTERVAL_S = 0.01
    FREQUENCY_BIN_STEP = 0.01

    BREATHING_MIN_FREQ = 0.15
    BREATHING_MAX_FREQ = 0.6
    BANDPASS_FILTER_ORDER = 4

    BREATHING_RATE_AGREEMENT_THRESHOLD_BPM = 3.0
    # バンドパスフィルタ端のロールオフ誤検出防止: 帯域幅に対する両端除外比率
    BREATHING_EDGE_MARGIN_RATIO = 0.15
    # find_peaks の prominence 閾値: スペクトル最大値に対する比率
    BREATHING_PEAK_PROMINENCE_RATIO = 0.05

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    contains_nan_or_inf = contains_nan_or_inf
    normalize_signal = normalize_signal
    drop_invalid_rows = drop_invalid_rows
    make_bins = make_bins
    remove_unnecessary_subcarriers = remove_unnecessary_subcarriers
    average_magnitude_by_frequency_bins = average_magnitude_by_frequency_bins

    apply_bandpass_filter = apply_bandpass_filter
    apply_fourier_transform = apply_fourier_transform
    estimate_breathing_rate = estimate_breathing_rate

    SUPPORTED_CSI_EXTENSIONS = SUPPORTED_CSI_EXTENSIONS

    _convert_csi_to_dataframe = _convert_csi_to_dataframe
    _convert_picoscenes_to_dataframe = _convert_picoscenes_to_dataframe
    _convert_picoscenes_to_dataframe_with_python = _convert_picoscenes_to_dataframe_with_python
    _convert_csv_to_dataframe_with_matlab = _convert_csv_to_dataframe_with_matlab
    _read_csv_directly = _read_csv_directly
    _resample_to_target_rate = _resample_to_target_rate
    _analyze_dataframe = _analyze_dataframe
    analyze_file = analyze_file
    analyze_pcap_file = analyze_pcap_file
    analyze_csi_file_with_picoscenes = analyze_csi_file_with_picoscenes
    parse_picoscenes_metadata = parse_picoscenes_metadata


pcap_analyzer = PCAPAnalyzer()
