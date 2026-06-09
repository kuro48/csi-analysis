"""
PCAPAnalyzer の単体テスト
"""

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pytest.importorskip("CSIKit")

from app.services.pcap_analyzer import PCAPAnalyzer
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
def test_compare_breathing_rate_methods_includes_music():
    analyzer = PCAPAnalyzer()

    comparison = analyzer.compare_breathing_rate_methods({
        "fft": 15.0,
        "wavelet": 14.4,
        "music": 15.2,
    })

    assert comparison["available_methods"] == ["fft", "wavelet", "music"]
    assert comparison["music_bpm"] == pytest.approx(15.2)
    assert comparison["is_consistent"] is True
    assert comparison["preferred_method"] == "fft"


@pytest.mark.unit
def test_analyze_dataframe_can_skip_breathing_estimation():
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
        captured["frame"] = frame.copy()
        return pd.DataFrame({"frequency": [0.01, 0.02], "1": [1.0, 2.0]})

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
    assert captured["frame"]["1"].tolist() == [0.0, 0.0, 1.0, 3.0]
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
        def analyze_file(self, file_path, include_breathing=True):
            assert file_path == "/tmp/base.csi"
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
