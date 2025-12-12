pragma circom 2.0.0;

include "../node_modules/circomlib/circuits/comparators.circom";

/**
 * CSI全DataFrame解析回路
 *
 * 全周波数ビン×全サブキャリアのFFTデータを入力として受け取り、
 * 呼吸検出に最適なサブキャリアと呼吸周波数を特定する
 *
 * 警告: この回路は非常に大規模で、証明生成に30分～数時間かかる可能性があります
 *
 * 入力データ構造:
 * - csi_amplitude[5000][256]: 5000周波数ビン × 256サブキャリア
 * - frequency_bins[5000]: 各周波数ビンの周波数値 (Hz × 10000)
 * - num_freq_points: 実際の周波数ポイント数
 * - num_subcarriers: 実際のサブキャリア数
 *
 * 固定小数点スケール: 10^4 (10000)
 * - 周波数: Hz × 10000 (例: 0.25Hz = 2500)
 * - 振幅: 整数値
 */

/**
 * 配列内の最大値を見つける
 */
template FindMax(N) {
    signal input values[N];
    signal output maxValue;
    signal output maxIndex;

    signal intermediate_max[N];
    signal intermediate_index[N];

    intermediate_max[0] <== values[0];
    intermediate_index[0] <== 0;

    component comparators[N-1];

    for (var i = 1; i < N; i++) {
        comparators[i-1] = GreaterThan(64);
        comparators[i-1].in[0] <== values[i];
        comparators[i-1].in[1] <== intermediate_max[i-1];

        // values[i] > intermediate_max[i-1] なら values[i]、そうでなければ intermediate_max[i-1]
        intermediate_max[i] <== comparators[i-1].out * (values[i] - intermediate_max[i-1]) + intermediate_max[i-1];
        intermediate_index[i] <== comparators[i-1].out * (i - intermediate_index[i-1]) + intermediate_index[i-1];
    }

    maxValue <== intermediate_max[N-1];
    maxIndex <== intermediate_index[N-1];
}

/**
 * 呼吸周波数帯域のパワーを計算
 */
template BreathingBandPower(MAX_FREQ_POINTS, MAX_SUBCARRIERS, SCALE) {
    // BREATHING_MIN = 1500 (0.15Hz × 10000)
    // BREATHING_MAX = 4000 (0.40Hz × 10000)
    var BREATHING_MIN = 1500;
    var BREATHING_MAX = 4000;

    signal input csi_amplitude[MAX_FREQ_POINTS][MAX_SUBCARRIERS];
    signal input frequency_bins[MAX_FREQ_POINTS];
    signal input num_freq_points;
    signal input num_subcarriers;

    signal output subcarrier_power[MAX_SUBCARRIERS];  // 各サブキャリアの呼吸帯域パワー

    // 各サブキャリアの呼吸帯域でのパワーを計算
    signal power_accumulator[MAX_SUBCARRIERS][MAX_FREQ_POINTS];

    component freq_check_min[MAX_FREQ_POINTS];
    component freq_check_max[MAX_FREQ_POINTS];
    signal in_breathing_band[MAX_FREQ_POINTS];

    // 各周波数ポイントが呼吸帯域内かチェック
    for (var f = 0; f < MAX_FREQ_POINTS; f++) {
        freq_check_min[f] = GreaterEqThan(32);
        freq_check_min[f].in[0] <== frequency_bins[f];
        freq_check_min[f].in[1] <== BREATHING_MIN;

        freq_check_max[f] = LessEqThan(32);
        freq_check_max[f].in[0] <== frequency_bins[f];
        freq_check_max[f].in[1] <== BREATHING_MAX;

        in_breathing_band[f] <== freq_check_min[f].out * freq_check_max[f].out;
    }

    // 各サブキャリアについて呼吸帯域のパワーを累積
    for (var s = 0; s < MAX_SUBCARRIERS; s++) {
        power_accumulator[s][0] <== csi_amplitude[0][s] * in_breathing_band[0];

        for (var f = 1; f < MAX_FREQ_POINTS; f++) {
            signal contribution;
            contribution <== csi_amplitude[f][s] * in_breathing_band[f];
            power_accumulator[s][f] <== power_accumulator[s][f-1] + contribution;
        }

        subcarrier_power[s] <== power_accumulator[s][MAX_FREQ_POINTS-1];
    }
}

/**
 * 最適なサブキャリアを選択（上位K個）
 */
template SelectTopKSubcarriers(MAX_SUBCARRIERS, K) {
    signal input subcarrier_power[MAX_SUBCARRIERS];
    signal output selected_indices[K];
    signal output selected_powers[K];

    // 簡易実装: K=4の場合
    // 実際にはソートアルゴリズムが必要だが、Circomでは複雑
    // ここでは最大値を4回見つける方式

    component max_finders[K];
    signal remaining_power[K][MAX_SUBCARRIERS];

    // 初期化: 最初の候補は全サブキャリア
    for (var s = 0; s < MAX_SUBCARRIERS; s++) {
        remaining_power[0][s] <== subcarrier_power[s];
    }

    for (var k = 0; k < K; k++) {
        max_finders[k] = FindMax(MAX_SUBCARRIERS);
        for (var s = 0; s < MAX_SUBCARRIERS; s++) {
            max_finders[k].values[s] <== remaining_power[k][s];
        }

        selected_indices[k] <== max_finders[k].maxIndex;
        selected_powers[k] <== max_finders[k].maxValue;

        // 次のイテレーション用: 選択されたサブキャリアを0にする
        if (k < K-1) {
            for (var s = 0; s < MAX_SUBCARRIERS; s++) {
                signal is_selected;
                component eq_check = IsEqual();
                eq_check.in[0] <== s;
                eq_check.in[1] <== max_finders[k].maxIndex;
                is_selected <== eq_check.out;

                // is_selected == 1 なら 0, そうでなければ remaining_power[k][s]
                remaining_power[k+1][s] <== remaining_power[k][s] * (1 - is_selected);
            }
        }
    }
}

/**
 * 選択されたサブキャリアでの呼吸周波数を検出
 */
template DetectBreathingFrequency(MAX_FREQ_POINTS, K, SCALE) {
    var BREATHING_MIN = 1500;
    var BREATHING_MAX = 4000;

    signal input csi_amplitude[MAX_FREQ_POINTS][K];  // K個の選択サブキャリアのみ
    signal input frequency_bins[MAX_FREQ_POINTS];
    signal input num_freq_points;

    signal output breathing_frequency;  // 呼吸周波数 (Hz × 10000)
    signal output peak_amplitude;       // ピーク振幅
    signal output confidence_score;     // 信頼度スコア (0-10000)

    // K個のサブキャリアの振幅を平均化
    signal avg_amplitude[MAX_FREQ_POINTS];
    signal amplitude_sum[MAX_FREQ_POINTS][K];

    for (var f = 0; f < MAX_FREQ_POINTS; f++) {
        amplitude_sum[f][0] <== csi_amplitude[f][0];

        for (var k = 1; k < K; k++) {
            amplitude_sum[f][k] <== amplitude_sum[f][k-1] + csi_amplitude[f][k];
        }

        // K で割る（整数除算）
        // 簡易版: Kで割らずに合計値を使用
        avg_amplitude[f] <== amplitude_sum[f][K-1];
    }

    // 呼吸帯域内でピークを検出
    component freq_check_min[MAX_FREQ_POINTS];
    component freq_check_max[MAX_FREQ_POINTS];
    signal in_breathing_band[MAX_FREQ_POINTS];
    signal masked_amplitude[MAX_FREQ_POINTS];

    for (var f = 0; f < MAX_FREQ_POINTS; f++) {
        freq_check_min[f] = GreaterEqThan(32);
        freq_check_min[f].in[0] <== frequency_bins[f];
        freq_check_min[f].in[1] <== BREATHING_MIN;

        freq_check_max[f] = LessEqThan(32);
        freq_check_max[f].in[0] <== frequency_bins[f];
        freq_check_max[f].in[1] <== BREATHING_MAX;

        in_breathing_band[f] <== freq_check_min[f].out * freq_check_max[f].out;
        masked_amplitude[f] <== avg_amplitude[f] * in_breathing_band[f];
    }

    // ピークを検出（最大振幅の周波数）
    component peak_finder = FindMax(MAX_FREQ_POINTS);
    for (var f = 0; f < MAX_FREQ_POINTS; f++) {
        peak_finder.values[f] <== masked_amplitude[f];
    }

    // ピークの周波数を取得
    signal peak_freq_index;
    peak_freq_index <== peak_finder.maxIndex;

    // frequency_bins[peak_freq_index] を取得
    // Circomでは動的インデックスアクセスができないため、ループで実現
    signal freq_selector[MAX_FREQ_POINTS];
    signal freq_contributions[MAX_FREQ_POINTS];

    for (var f = 0; f < MAX_FREQ_POINTS; f++) {
        component is_peak = IsEqual();
        is_peak.in[0] <== f;
        is_peak.in[1] <== peak_freq_index;
        freq_selector[f] <== is_peak.out;
        freq_contributions[f] <== frequency_bins[f] * freq_selector[f];
    }

    signal freq_sum[MAX_FREQ_POINTS];
    freq_sum[0] <== freq_contributions[0];
    for (var f = 1; f < MAX_FREQ_POINTS; f++) {
        freq_sum[f] <== freq_sum[f-1] + freq_contributions[f];
    }

    breathing_frequency <== freq_sum[MAX_FREQ_POINTS-1];
    peak_amplitude <== peak_finder.maxValue;

    // 信頼度スコア: ピーク振幅 / 平均振幅の比率（簡易版）
    // 実際の実装では witness で計算して検証
    confidence_score <== SCALE;  // プレースホルダー
}

/**
 * メイン回路: CSI全DataFrame解析
 */
template CSIFullDataFrameAnalyzer(MAX_FREQ_POINTS, MAX_SUBCARRIERS, K, SCALE) {
    // MAX_FREQ_POINTS: 最大周波数ポイント数（5000）
    // MAX_SUBCARRIERS: 最大サブキャリア数（256）
    // K: 選択するサブキャリア数（4）
    // SCALE: 固定小数点スケール（10000）

    signal input csi_amplitude[MAX_FREQ_POINTS][MAX_SUBCARRIERS];
    signal input frequency_bins[MAX_FREQ_POINTS];
    signal input num_freq_points;
    signal input num_subcarriers;

    signal output best_subcarrier_indices[K];
    signal output breathing_frequency;
    signal output confidence_score;
    signal output peak_amplitude;

    // ステップ1: 各サブキャリアの呼吸帯域パワーを計算
    component power_calc = BreathingBandPower(MAX_FREQ_POINTS, MAX_SUBCARRIERS, SCALE);
    for (var f = 0; f < MAX_FREQ_POINTS; f++) {
        power_calc.frequency_bins[f] <== frequency_bins[f];
        for (var s = 0; s < MAX_SUBCARRIERS; s++) {
            power_calc.csi_amplitude[f][s] <== csi_amplitude[f][s];
        }
    }
    power_calc.num_freq_points <== num_freq_points;
    power_calc.num_subcarriers <== num_subcarriers;

    // ステップ2: 最適なK個のサブキャリアを選択
    component subcarrier_selector = SelectTopKSubcarriers(MAX_SUBCARRIERS, K);
    for (var s = 0; s < MAX_SUBCARRIERS; s++) {
        subcarrier_selector.subcarrier_power[s] <== power_calc.subcarrier_power[s];
    }

    for (var k = 0; k < K; k++) {
        best_subcarrier_indices[k] <== subcarrier_selector.selected_indices[k];
    }

    // ステップ3: 選択されたサブキャリアでの呼吸周波数を検出
    // 選択されたサブキャリアのデータを抽出
    signal selected_csi[MAX_FREQ_POINTS][K];

    for (var f = 0; f < MAX_FREQ_POINTS; f++) {
        for (var k = 0; k < K; k++) {
            // 動的インデックスアクセスの代替実装
            signal selector[MAX_SUBCARRIERS];
            signal contributions[MAX_SUBCARRIERS];

            for (var s = 0; s < MAX_SUBCARRIERS; s++) {
                component eq_check = IsEqual();
                eq_check.in[0] <== s;
                eq_check.in[1] <== subcarrier_selector.selected_indices[k];
                selector[s] <== eq_check.out;
                contributions[s] <== csi_amplitude[f][s] * selector[s];
            }

            signal sum[MAX_SUBCARRIERS];
            sum[0] <== contributions[0];
            for (var s = 1; s < MAX_SUBCARRIERS; s++) {
                sum[s] <== sum[s-1] + contributions[s];
            }

            selected_csi[f][k] <== sum[MAX_SUBCARRIERS-1];
        }
    }

    component freq_detector = DetectBreathingFrequency(MAX_FREQ_POINTS, K, SCALE);
    for (var f = 0; f < MAX_FREQ_POINTS; f++) {
        freq_detector.frequency_bins[f] <== frequency_bins[f];
        for (var k = 0; k < K; k++) {
            freq_detector.csi_amplitude[f][k] <== selected_csi[f][k];
        }
    }
    freq_detector.num_freq_points <== num_freq_points;

    breathing_frequency <== freq_detector.breathing_frequency;
    confidence_score <== freq_detector.confidence_score;
    peak_amplitude <== freq_detector.peak_amplitude;
}

// メインインスタンス
// 警告: このサイズは非常に大きく、コンパイルと証明生成に時間がかかります
component main {public [frequency_bins]} = CSIFullDataFrameAnalyzer(5000, 256, 4, 10000);
