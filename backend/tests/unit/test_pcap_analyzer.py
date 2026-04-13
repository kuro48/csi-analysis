"""
PCAPAnalyzer の単体テスト
"""

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pytest.importorskip("CSIKit")

from app.services.pcap_analyzer import PCAPAnalyzer


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
