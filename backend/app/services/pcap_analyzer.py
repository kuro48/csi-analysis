"""
PCAP解析サービス
Wi-Fi CSIデータをPCAPファイルから抽出・解析する。
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
    _compute_music_pseudospectrum,
    apply_bandpass_filter,
    apply_fourier_transform,
    apply_music_transform,
    apply_wavelet_transform,
    compare_breathing_rate_methods,
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
from app.services.pcap_analyzer_zkp import (
    analyze_and_generate_zkp,
    extract_full_subcarrier_vectors,
    extract_matrix_for_zkp,
    extract_music_matrix_for_zkp,
    prepare_zkp_vectors_from_fft,
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
    WAVELET_DOWNSAMPLE_INTERVAL_S = 0.2  # 5 Hz: バンドパス後(0.5Hz上限)はナイキスト条件を満たす
    FREQUENCY_BIN_STEP = 0.01

    BREATHING_MIN_FREQ = 0.16
    BREATHING_MAX_FREQ = 0.6
    BANDPASS_FILTER_ORDER = 4

    ZKP_FREQ_START = 0.0
    ZKP_FREQ_END = 0.60
    ZKP_FREQ_STEP = 0.02
    ZKP_VECTOR_DIM = 4
    ZKP_SCALE = 10000
    MAX_FREQ_POINTS = 5000
    MAX_SUBCARRIERS = 256

    WAVELET_FREQ_MIN = 0.01
    WAVELET_FREQ_MAX = 2.0
    WAVELET_N_FREQS = 100
    WAVELET_NAME = "cmor1.5-1.0"
    WAVELET_FFT_METHOD_MIN_SIGNAL_LEN = 256

    BREATHING_RATE_AGREEMENT_THRESHOLD_BPM = 3.0
    # バンドパスフィルタ端のロールオフ誤検出防止: 帯域幅に対する両端除外比率
    BREATHING_EDGE_MARGIN_RATIO = 0.15
    # find_peaks の prominence 閾値: スペクトル最大値に対する比率
    BREATHING_PEAK_PROMINENCE_RATIO = 0.05

    MUSIC_DOWNSAMPLE_INTERVAL_S = 0.1  # 10 Hz, matching the MUSIC paper setup.
    MUSIC_FREQ_MIN = 0.16
    MUSIC_FREQ_MAX = 0.6
    MUSIC_N_FREQS = 128
    MUSIC_EMBEDDING_DIM = 32
    MUSIC_MODEL_ORDER = 2

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
    apply_wavelet_transform = apply_wavelet_transform
    _compute_music_pseudospectrum = _compute_music_pseudospectrum
    apply_music_transform = apply_music_transform
    estimate_breathing_rate = estimate_breathing_rate
    compare_breathing_rate_methods = compare_breathing_rate_methods

    extract_full_subcarrier_vectors = extract_full_subcarrier_vectors
    extract_matrix_for_zkp = extract_matrix_for_zkp
    extract_music_matrix_for_zkp = extract_music_matrix_for_zkp
    prepare_zkp_vectors_from_fft = prepare_zkp_vectors_from_fft
    analyze_and_generate_zkp = analyze_and_generate_zkp

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
