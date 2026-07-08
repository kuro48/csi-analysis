"""
breathing_pipeline（5-1.ipynb 移植パイプライン）の単体テスト
"""

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from app.services.breathing_pipeline import (  # noqa: E402
    BPM_MAX,
    BPM_MIN,
    FS,
    HIGHCUT,
    LOWCUT,
    ZKP_SIGNAL_SCALE,
    ZKP_T,
    bandpass_filter,
    prepare_breathing_zkp_input,
    respiration_score_fft,
    select_respiration_pc,
    select_subcarriers_by_snr,
)

BREATHING_HZ = 0.25  # 15 bpm


def _make_time_axis(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * FS)) / FS


@pytest.mark.unit
def test_bandpass_filter_keeps_breathing_band_and_removes_noise():
    # Arrange: 呼吸帯域内 0.25Hz + 帯域外 5Hz の合成信号
    t = _make_time_axis(60)
    in_band = np.sin(2 * np.pi * BREATHING_HZ * t)
    out_band = np.sin(2 * np.pi * 5.0 * t)
    data = (in_band + out_band)[:, np.newaxis]

    # Act
    filtered = bandpass_filter(data, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT)

    # Assert: 帯域内成分の相関は残り、帯域外成分の振幅は大きく減衰する
    corr = np.corrcoef(filtered[:, 0], in_band)[0, 1]
    assert corr > 0.9
    assert np.std(filtered[:, 0]) < 0.8 * np.std(data[:, 0])


@pytest.mark.unit
def test_bandpass_filter_rejects_invalid_band():
    with pytest.raises(ValueError):
        bandpass_filter(np.zeros((100, 1)), fs=FS, lowcut=0.0, highcut=1.0)


@pytest.mark.unit
def test_select_subcarriers_by_snr_prefers_breathing_subcarriers():
    # Arrange: 前半5列は呼吸信号入り、後半5列は高周波ノイズのみ
    rng = np.random.default_rng(42)
    t = _make_time_axis(30)
    breathing = np.sin(2 * np.pi * BREATHING_HZ * t)
    high_noise = np.sin(2 * np.pi * 10.0 * t)

    columns = []
    for _ in range(5):
        columns.append(breathing + 0.05 * rng.standard_normal(len(t)))
    for _ in range(5):
        columns.append(high_noise + 0.05 * rng.standard_normal(len(t)))
    amplitude = np.stack(columns, axis=1) + 10.0

    # Act
    selected, indices, snr = select_subcarriers_by_snr(
        amplitude, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT, n_select=5
    )

    # Assert: SNR 上位5列は呼吸信号入りの列（index 0-4）
    assert selected.shape == (len(t), 5)
    assert set(indices.tolist()) == {0, 1, 2, 3, 4}
    assert snr.shape == (10,)


@pytest.mark.unit
def test_respiration_score_fft_is_higher_for_in_band_signal():
    t = _make_time_axis(30)
    in_band = np.sin(2 * np.pi * BREATHING_HZ * t)
    out_band = np.sin(2 * np.pi * 5.0 * t)

    score_in = respiration_score_fft(in_band, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT)
    score_out = respiration_score_fft(out_band, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT)

    assert score_in > 0.9
    assert score_out < 0.1
    assert score_in > score_out


@pytest.mark.unit
def test_select_respiration_pc_picks_breathing_component():
    # Arrange: PC2 だけが呼吸信号
    rng = np.random.default_rng(0)
    t = _make_time_axis(30)
    pcs = np.stack(
        [
            np.sin(2 * np.pi * 3.0 * t),
            np.sin(2 * np.pi * BREATHING_HZ * t),
            rng.standard_normal(len(t)),
        ],
        axis=1,
    )

    # Act
    respiration_pc, best_idx, scores = select_respiration_pc(
        pcs, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT
    )

    # Assert
    assert best_idx == 1
    assert len(scores) == 3
    np.testing.assert_array_equal(respiration_pc, pcs[:, 1])


@pytest.mark.unit
def test_estimate_breathing_rate_by_vmd_recovers_15bpm():
    pytest.importorskip("vmdpy")
    from app.services.breathing_pipeline import (
        VMD_ALPHA,
        VMD_DC,
        VMD_INIT,
        VMD_K,
        VMD_TAU,
        VMD_TOL,
        estimate_breathing_rate_by_vmd_global_peak,
    )

    # Arrange: 15bpm の呼吸様信号 + 微小ノイズ
    rng = np.random.default_rng(7)
    t = _make_time_axis(60)
    signal = np.sin(2 * np.pi * BREATHING_HZ * t) + 0.05 * rng.standard_normal(len(t))

    # Act
    _, mode_infos, best_info = estimate_breathing_rate_by_vmd_global_peak(
        signal=signal, fs=FS, bpm_min=BPM_MIN, bpm_max=BPM_MAX,
        K=VMD_K, alpha=VMD_ALPHA, tau=VMD_TAU, DC=VMD_DC, init=VMD_INIT, tol=VMD_TOL,
    )

    # Assert: 推定bpmが 15±1、選択モードは呼吸範囲内
    assert len(mode_infos) == VMD_K
    assert best_info["is_valid"]
    assert abs(best_info["global_peak_bpm"] - 15.0) < 1.0


@pytest.mark.unit
def test_prepare_breathing_zkp_input_shape_and_range():
    # Arrange: 100Hz の 0.25Hz 正弦波 40 秒
    t = _make_time_axis(40)
    vmd_mode = np.sin(2 * np.pi * BREATHING_HZ * t) + 3.0  # DCオフセット付き

    # Act
    zkp_input = prepare_breathing_zkp_input(vmd_mode)

    # Assert: 長さ・整数化・スケール・ゼロ中心化
    assert len(zkp_input) == ZKP_T
    assert all(isinstance(v, int) for v in zkp_input)
    assert max(abs(v) for v in zkp_input) <= ZKP_SIGNAL_SCALE
    assert abs(sum(zkp_input)) < ZKP_T  # 平均がほぼゼロ


@pytest.mark.unit
def test_prepare_breathing_zkp_input_pads_short_signal():
    zkp_input = prepare_breathing_zkp_input(np.ones(100))  # 5Hz換算で5サンプルのみ

    assert len(zkp_input) == ZKP_T


@pytest.mark.unit
def test_prepare_breathing_zkp_input_rejects_invalid_fs():
    with pytest.raises(ValueError):
        prepare_breathing_zkp_input(np.ones(100), fs=1.0, target_fs=5.0)


@pytest.mark.unit
def test_run_breathing_pipeline_from_matrix_end_to_end():
    pytest.importorskip("sklearn")
    pytest.importorskip("vmdpy")
    from app.services.breathing_pipeline import run_breathing_pipeline_from_matrix

    # Arrange: 15bpm 呼吸で変調された複素CSI行列（40秒 × 20サブキャリア）
    rng = np.random.default_rng(1)
    t = _make_time_axis(40)
    breathing = np.sin(2 * np.pi * BREATHING_HZ * t)
    subcarriers = []
    for k in range(20):
        amp = 10.0 + (0.5 + 0.05 * k) * breathing + 0.05 * rng.standard_normal(len(t))
        phase = rng.uniform(0, 2 * np.pi)
        subcarriers.append(amp * np.exp(1j * phase))
    csi_matrix = np.stack(subcarriers, axis=1)

    # Act
    result = run_breathing_pipeline_from_matrix(csi_matrix)

    # Assert: 15bpm 近傍を推定し、ZKP入力が回路仕様を満たす
    assert abs(result["breathing_rate_bpm"] - 15.0) < 1.5
    assert result["n_subcarriers_total"] == 20
    assert len(result["zkp_input"]) == ZKP_T
    assert max(abs(v) for v in result["zkp_input"]) <= ZKP_SIGNAL_SCALE
    assert result["bpm_range"] == {"min": BPM_MIN, "max": BPM_MAX}
    assert len(result["vmd_mode_summaries"]) == 5
    # 判定キーが Python 側に存在しないこと（判定は ZKP 回路の責務）
    assert "is_breathing" not in result
    assert "is_normal" not in result
