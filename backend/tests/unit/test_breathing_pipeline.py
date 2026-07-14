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
    VMD_K,
    ZKP_CERT_MODE_MAX_ABS,
    ZKP_CERT_SIGNAL_SCALE,
    ZKP_SIGNAL_SCALE,
    ZKP_T,
    bandpass_filter,
    prepare_breathing_certificate_input,
    prepare_breathing_zkp_input,
    prepare_zkvm_input,
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
    selected, indices, snr = select_subcarriers_by_snr(amplitude, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT, n_select=5)

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
    respiration_pc, best_idx, scores = select_respiration_pc(pcs, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT)

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
        signal=signal,
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
def test_prepare_zkvm_input_is_flattened_bounded_and_deterministic():
    matrix = np.array(
        [
            [3 + 4j, 1 + 0j, 0 + 2j],
            [0 + 5j, 2 + 0j, 0 + 3j],
            [4 + 3j, 3 + 0j, 0 + 4j],
        ],
        dtype=np.complex128,
    )

    first = prepare_zkvm_input(matrix, scale=100)
    second = prepare_zkvm_input(matrix, scale=100)

    assert first == second
    assert first["samples"] == 3
    assert first["subcarriers"] == 3
    assert len(first["amplitudes"]) == 9
    assert all(isinstance(value, int) for value in first["amplitudes"])
    assert max(first["amplitudes"]) <= 100
    assert len(first["input_commitment"]) == 64


# ---------------------------------------------------------------------------
# 証明書回路入力（案A）
# ---------------------------------------------------------------------------
def _make_certificate_signals(freqs, weights, seconds=40.0):
    """freqs 各周波数の正弦波をモードとし、その総和＋DCオフセットを VMD 入力とする。

    Σ_k modes = 呼吸PC（中心化前）となるので、中心化後の再構成性が保たれる。
    """
    t = _make_time_axis(seconds)
    modes = np.vstack([w * np.sin(2 * np.pi * f * t) for f, w in zip(freqs, weights)])
    respiration_pc = modes.sum(axis=0) + 4.0  # DCオフセット（中心化処理を検証）
    return respiration_pc, modes


@pytest.mark.unit
def test_prepare_breathing_certificate_input_shapes_and_onehot():
    # Arrange: mode0 = 12bpm(0.2Hz), 他は別帯域
    freqs = [0.2, 0.7, 0.05, 1.3, 2.0]
    weights = [1.0, 0.3, 0.3, 0.2, 0.2]
    respiration_pc, modes = _make_certificate_signals(freqs, weights)

    # Act
    out = prepare_breathing_certificate_input(respiration_pc, modes, selected_mode_index=0)

    # Assert: 形状・one-hot・整数化・スケール上限
    assert len(out["vmdInput"]) == ZKP_T
    assert len(out["modes"]) == VMD_K
    assert all(len(m) == ZKP_T for m in out["modes"])
    assert out["sel"] == [1, 0, 0, 0, 0]
    assert sum(out["sel"]) == 1
    assert all(isinstance(v, int) for v in out["vmdInput"])
    assert max(abs(v) for v in out["vmdInput"]) <= ZKP_CERT_SIGNAL_SCALE
    assert out["diagnostics"]["max_mode_abs"] <= ZKP_CERT_MODE_MAX_ABS


@pytest.mark.unit
def test_prepare_breathing_certificate_input_reconstruction_holds():
    # Arrange: モードの総和が信号を厳密に再構成するケース
    freqs = [0.2, 0.6, 0.9, 1.2, 1.8]
    weights = [1.0, 0.4, 0.3, 0.2, 0.2]
    respiration_pc, modes = _make_certificate_signals(freqs, weights)

    # Act
    out = prepare_breathing_certificate_input(respiration_pc, modes, selected_mode_index=0)
    diag = out["diagnostics"]

    # Assert: 整数領域でも Σ modes ≈ vmdInput（回路のハード制約を満たす）
    assert diag["recon_ok"] is True
    assert diag["recon_error_ratio"] < diag["recon_error_ratio_threshold"]
    # 手計算でも再構成誤差比が小さいことを確認
    recon = np.sum(np.array(out["modes"], dtype=float), axis=0)
    sig = np.array(out["vmdInput"], dtype=float)
    ratio = np.sum((recon - sig) ** 2) / (np.sum(sig**2) + 1e-12)
    assert ratio < 0.5


@pytest.mark.unit
def test_prepare_breathing_certificate_input_common_scale_bounds_modes():
    # Arrange: 単一モードが信号より大きい（共通スケールで mode 上限を超えないこと）
    freqs = [0.2, 0.25, 0.3, 0.35, 0.4]
    weights = [5.0, 5.0, 5.0, 5.0, 5.0]  # 各モードが大振幅
    respiration_pc, modes = _make_certificate_signals(freqs, weights)

    # Act
    out = prepare_breathing_certificate_input(respiration_pc, modes, selected_mode_index=0)

    # Assert: 全モードが回路のビット幅上限内に収まる
    assert out["diagnostics"]["max_mode_abs"] <= ZKP_CERT_MODE_MAX_ABS


@pytest.mark.unit
def test_prepare_breathing_certificate_input_rejects_bad_index():
    _, modes = _make_certificate_signals([0.2, 0.5, 0.7, 0.9, 1.1], [1, 1, 1, 1, 1])
    with pytest.raises(ValueError):
        prepare_breathing_certificate_input(modes.sum(axis=0), modes, selected_mode_index=99)


@pytest.mark.unit
def test_prepare_breathing_certificate_input_rejects_non_2d_modes():
    with pytest.raises(ValueError):
        prepare_breathing_certificate_input(np.ones(100), np.ones(100), selected_mode_index=0)


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
    # 呼吸波形（Webサイトの波形表示・結果ダウンロード用）が全サンプル分含まれること
    assert len(result["respiration_waveform"]) == result["n_samples"]
    assert all(isinstance(v, float) for v in result["respiration_waveform"])
    assert len(result["zkp_input"]) == ZKP_T
    assert max(abs(v) for v in result["zkp_input"]) <= ZKP_SIGNAL_SCALE
    # 証明書回路入力（案A）が回路仕様を満たすこと
    cert = result["certificate_input"]
    assert len(cert["vmdInput"]) == ZKP_T
    assert len(cert["modes"]) == VMD_K
    assert all(len(m) == ZKP_T for m in cert["modes"])
    assert sum(cert["sel"]) == 1
    assert cert["diagnostics"]["max_mode_abs"] <= ZKP_CERT_MODE_MAX_ABS
    assert result["bpm_range"] == {"min": BPM_MIN, "max": BPM_MAX}
    assert len(result["vmd_mode_summaries"]) == 5
    # 判定キーが Python 側に存在しないこと（判定は ZKP 回路の責務）
    assert "is_breathing" not in result
    assert "is_normal" not in result
