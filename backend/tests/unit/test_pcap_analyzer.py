"""
PCAPAnalyzer の単体テスト
"""

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pytest.importorskip("CSIKit")

from app.services.pcap_analyzer import PCAPAnalyzer
from app.services.pcap_analyzer_common import extract_phase_dataframe
from app.models.base_csi import BaseCSI
from app.services import base_csi as base_csi_service_module
from app.services.base_csi import BaseCSIService


@pytest.mark.unit
def test_apply_music_transform_estimates_breathing_rate():
    analyzer = PCAPAnalyzer()
    target_bpm = 15.0
    target_hz = target_bpm / 60.0
    sample_count = 1200
    time_axis = np.arange(sample_count) * analyzer.DOWNSAMPLE_INTERVAL_S
    signal = np.sin(2 * np.pi * target_hz * time_axis)

    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=sample_count, freq="10ms"),
        "1": signal,
        "2": signal * 0.8,
        "3": signal * 1.1,
    })

    music_df = analyzer.apply_music_transform(df, analyzer.DOWNSAMPLE_INTERVAL_S)

    assert not music_df.empty
    assert "frequency" in music_df.columns

    estimated_bpm = analyzer.estimate_breathing_rate(music_df, freq_col="frequency")

    assert estimated_bpm is not None
    assert estimated_bpm == pytest.approx(target_bpm, abs=1.0)


@pytest.mark.unit
def test_compute_music_pseudospectrum_matches_paper_noise_fft_method():
    analyzer = PCAPAnalyzer()
    sampling_interval = 0.1
    embedding_dim = 8
    model_order = 1
    n_fft = 64
    time_axis = np.arange(80) * sampling_interval
    signal = (
        np.sin(2 * np.pi * 0.25 * time_axis)
        + 0.25 * np.sin(2 * np.pi * 0.42 * time_axis)
    )
    frequencies = np.arange(n_fft, dtype=np.float64) * (1.0 / sampling_interval) / n_fft

    cleaned = signal - np.mean(signal)
    windows = np.lib.stride_tricks.sliding_window_view(cleaned, embedding_dim)
    covariance = (windows.T @ windows) / (embedding_dim - 1)
    _, eigvecs = np.linalg.eigh(covariance)
    noise_subspace = eigvecs[:, : embedding_dim - model_order]
    noise_fft = np.fft.fft(noise_subspace, n=n_fft, axis=0)
    denominator = np.sum(np.abs(noise_fft) ** 2, axis=1)
    expected = 1.0 / np.maximum(denominator, 1e-12)

    actual = analyzer._compute_music_pseudospectrum(
        signal,
        sampling_interval,
        frequencies,
        embedding_dim=embedding_dim,
        model_order=model_order,
    )

    assert actual == pytest.approx(expected.astype(np.float32), rel=1e-6, abs=1e-6)


@pytest.mark.unit
def test_analyze_dataframe_runs_music_at_paper_10hz_rate():
    analyzer = PCAPAnalyzer()
    sample_count = 1200
    time_axis = np.arange(sample_count) * analyzer.DOWNSAMPLE_INTERVAL_S
    signal = np.sin(2 * np.pi * 0.25 * time_axis) + 3.0
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=sample_count, freq="10ms"),
        "1": signal,
        "2": signal * 0.9,
    })

    captured_intervals = []

    def fake_music(frame, sampling_interval):
        captured_intervals.append(sampling_interval)
        return pd.DataFrame({"frequency": [0.25], "1": [1.0]})

    analyzer.apply_music_transform = fake_music

    analyzer._analyze_dataframe(
        df=df,
        no_frames=sample_count,
        no_subcarriers=2,
        include_wavelet=False,
        include_music=True,
        include_breathing=True,
    )

    assert analyzer.MUSIC_DOWNSAMPLE_INTERVAL_S == pytest.approx(0.1)
    assert captured_intervals == [pytest.approx(analyzer.MUSIC_DOWNSAMPLE_INTERVAL_S)]


@pytest.mark.unit
def test_compare_breathing_rate_methods_includes_music():
    analyzer = PCAPAnalyzer()

    comparison = analyzer.compare_breathing_rate_methods({
        "fft": 15.0,
        "wavelet": 14.4,
        "music": 15.2,
    })

    assert comparison["fft_bpm"] == pytest.approx(15.0)
    assert comparison["wavelet_bpm"] == pytest.approx(14.4)
    assert comparison["music_bpm"] == pytest.approx(15.2)


@pytest.mark.unit
def test_analyze_dataframe_can_skip_breathing_estimation():
    analyzer = PCAPAnalyzer()
    sample_count = 1200
    signal = np.sin(2 * np.pi * 0.2 * np.arange(sample_count) * analyzer.DOWNSAMPLE_INTERVAL_S)
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=sample_count, freq="10ms"),
        "1": signal + 3.0,
        "2": signal * 0.5 + 6.0,
    })

    result = analyzer._analyze_dataframe(
        df=df,
        no_frames=sample_count,
        no_subcarriers=2,
        include_wavelet=False,
        include_music=False,
        include_breathing=False,
    )

    assert not result["fft"].empty
    assert result["breathing_rate_fft_bpm"] is None
    assert result["breathing_rate_wavelet_bpm"] is None
    assert result["breathing_rate_music_bpm"] is None
    assert result["breathing_rate_comparison"] is None
    assert result["subcarrier_medians"] == {
        "1": pytest.approx(float(np.median(df["1"]))),
        "2": pytest.approx(float(np.median(df["2"]))),
    }


@pytest.mark.unit
def test_analyze_dataframe_uses_only_magnitude_columns_and_subtracts_background():
    analyzer = PCAPAnalyzer()
    captured = {}

    def fake_fft(frame, sampling_interval):
        captured.setdefault("frame", frame.copy())
        return pd.DataFrame({"frequency": [0.2, 0.3], "1": [1.0, 2.0]})

    analyzer.apply_fourier_transform = fake_fft

    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="10ms"),
        "1": [1.0, 3.0, 5.0, 7.0],
        "1_phase": [100.0, 101.0, 102.0, 103.0],
    })

    result = analyzer._analyze_dataframe(
        df=df,
        no_frames=4,
        no_subcarriers=1,
        include_wavelet=False,
        include_music=False,
        include_breathing=False,
        background_subcarrier_medians={"1": 4.0},
    )

    assert not result["fft"].empty
    assert captured["frame"]["1"].tolist() == pytest.approx([0.0, 0.0, 1.0, 3.0], abs=1e-9)
    assert captured["frame"]["1_phase"].tolist() == [100.0, 101.0, 102.0, 103.0]
    assert result["subcarrier_medians"] == {"1": pytest.approx(4.0)}


@pytest.mark.unit
def test_frequency_transforms_ignore_phase_columns():
    analyzer = PCAPAnalyzer()
    sample_count = 32
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=sample_count, freq="10ms"),
        "1": np.sin(np.arange(sample_count)),
        "1_phase": np.arange(sample_count, dtype=float),
    })

    fft_df = analyzer.apply_fourier_transform(df, analyzer.DOWNSAMPLE_INTERVAL_S)

    assert "1" in fft_df.columns
    assert "1_phase" not in fft_df.columns


@pytest.mark.unit
def test_extract_phase_dataframe_renames_and_detrends():
    """位相列が抽出され、列名がリネームされ、線形 detrend が適用される。"""
    sample_count = 64
    timestamps = pd.date_range("2026-01-01", periods=sample_count, freq="10ms")
    # 線形ランプ位相 (CFO/SFO 由来のドリフト相当) → detrend で 0 になるはず
    linear_ramp = np.linspace(0, 6 * np.pi, sample_count)
    df = pd.DataFrame({
        "timestamp": timestamps,
        "-1": np.random.randn(sample_count),
        "1": np.random.randn(sample_count),
        "-1_phase": linear_ramp,
        "1_phase": -linear_ramp,
    })
    df.attrs["bandwidth_mhz"] = 80
    df.attrs["band"] = "5GHz"

    result = extract_phase_dataframe(df)

    assert list(result.columns) == ["timestamp", "-1", "1"]
    assert result.attrs.get("bandwidth_mhz") == 80
    assert result.attrs.get("band") == "5GHz"
    assert len(result) == sample_count
    # 線形ランプは detrend で消えるため、残差は数値誤差レベル
    assert np.allclose(result["-1"].values, 0.0, atol=1e-9)
    assert np.allclose(result["1"].values, 0.0, atol=1e-9)


@pytest.mark.unit
def test_extract_phase_dataframe_returns_empty_when_no_phase_columns():
    """位相列が無い DataFrame は空 DataFrame を返す。"""
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="10ms"),
        "1": [1.0, 2.0, 3.0, 4.0],
        "2": [5.0, 6.0, 7.0, 8.0],
    })

    result = extract_phase_dataframe(df)

    assert result.empty


@pytest.mark.unit
def test_extract_phase_dataframe_unwraps_2pi_jumps():
    """位相に 2π ジャンプが含まれている場合、np.unwrap が適用される。"""
    sample_count = 16
    # 0, 1, 2, ..., 7 (rad) のような連続値に強制的に 2π ジャンプを入れる
    raw_phase = np.arange(sample_count, dtype=np.float64) * 0.5
    raw_phase[8:] -= 2 * np.pi  # 8 番目で 2π 落ちる
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=sample_count, freq="10ms"),
        "1_phase": raw_phase,
    })

    result = extract_phase_dataframe(df)

    # 線形 detrend がかかるので値は 0 に近いが、unwrap が無いとジャンプが残って detrend だけでは消えない。
    # 検証: unwrap 後にきれいな線形になっていれば detrend で全要素が 0 近傍に落ちる。
    assert np.allclose(result["1"].values, 0.0, atol=1e-9)


@pytest.mark.unit
def test_analyze_dataframe_includes_phase_results_when_phase_columns_present():
    """位相列を含む DataFrame の場合、戻り値辞書に位相パイプライン結果が含まれる。"""
    analyzer = PCAPAnalyzer()
    sample_count = 1200
    time_axis = np.arange(sample_count) * analyzer.DOWNSAMPLE_INTERVAL_S
    breathing_hz = 0.25  # 15 BPM
    amp_signal = np.sin(2 * np.pi * breathing_hz * time_axis) + 3.0
    # 位相にも同じ周波数成分を載せる
    phase_signal = 0.5 * np.sin(2 * np.pi * breathing_hz * time_axis)

    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=sample_count, freq="10ms"),
        "1": amp_signal,
        "2": amp_signal * 0.9,
        "1_phase": phase_signal,
        "2_phase": phase_signal * 0.95,
    })

    result = analyzer._analyze_dataframe(
        df=df,
        no_frames=sample_count,
        no_subcarriers=2,
        include_wavelet=False,
        include_music=False,
        include_breathing=True,
    )

    assert "fft_phase" in result
    assert "wavelet_phase" in result
    assert "music_phase" in result
    assert "breathing_rate_fft_phase_bpm" in result
    assert "breathing_rate_phase_comparison" in result
    assert not result["fft_phase"].empty
    # 位相 FFT からも呼吸数が推定できているはず
    assert result["breathing_rate_fft_phase_bpm"] is not None


@pytest.mark.unit
def test_analyze_dataframe_phase_fields_empty_when_phase_columns_absent():
    """位相列が無い場合、戻り値辞書の位相フィールドは空 / None になる。"""
    analyzer = PCAPAnalyzer()
    sample_count = 120
    signal = np.sin(2 * np.pi * 0.2 * np.arange(sample_count) * analyzer.DOWNSAMPLE_INTERVAL_S)
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=sample_count, freq="10ms"),
        "1": signal + 3.0,
        "2": signal * 0.5 + 6.0,
    })

    result = analyzer._analyze_dataframe(
        df=df,
        no_frames=sample_count,
        no_subcarriers=2,
        include_wavelet=False,
        include_music=False,
        include_breathing=True,
    )

    assert result["fft_phase"].empty
    assert result["wavelet_phase"].empty
    assert result["music_phase"].empty
    assert result["breathing_rate_fft_phase_bpm"] is None
    assert result["breathing_rate_wavelet_phase_bpm"] is None
    assert result["breathing_rate_music_phase_bpm"] is None
    assert result["breathing_rate_phase_comparison"] is None


@pytest.mark.unit
def test_process_base_csi_registration_saves_subcarrier_medians(db, monkeypatch):
    base_csi = BaseCSI(
        name="base.csi",
        fft_dataframe={},
        source_pcap_path="/tmp/base.csi",
        source_pcap_size=128,
        status="processing",
    )
    db.add(base_csi)
    db.commit()
    db.refresh(base_csi)

    class FakeAnalyzer:
        def analyze_file(
            self,
            file_path,
            include_wavelet=True,
            include_music=True,
            include_breathing=True,
        ):
            assert file_path == "/tmp/base.csi"
            assert include_wavelet is False
            assert include_music is False
            assert include_breathing is False
            return {
                "fft": pd.DataFrame({"freq_interval": ["[0.0, 0.01)"], "1": [1.0]}),
                "wavelet": pd.DataFrame(),
                "music": pd.DataFrame(),
                "subcarrier_medians": {"1": 2.5, "2": 4.0},
            }

    monkeypatch.setattr(base_csi_service_module, "PCAPAnalyzer", FakeAnalyzer)

    processed = BaseCSIService.process_base_csi_registration(db, base_csi.id)

    assert processed.status == "completed"
    assert processed.subcarrier_medians == {"1": 2.5, "2": 4.0}
