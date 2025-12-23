pragma circom 2.0.0;

include "../node_modules/circomlib/circuits/comparators.circom";

/**
 * 全サブキャリア × 全周波数ポイントのコサイン類似度計算回路
 *
 * 呼吸周波数帯域（0.15～0.4Hz）の全データを使用してコサイン類似度を計算
 *
 * パラメータ:
 * - NUM_FREQ_POINTS: 周波数ポイント数（呼吸周波数帯域内）
 * - NUM_SUBCARRIERS: サブキャリア数
 * - TOTAL_DIM: NUM_FREQ_POINTS × NUM_SUBCARRIERS（総次元数）
 * - SCALE: 固定小数点スケール (10^4 = 10000)
 *
 * 入力:
 * - referenceMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS]: 参照CSIデータ（ベースCSI）
 * - candidateMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS]: 候補CSIデータ（アップロード）
 *
 * 出力:
 * - similarity: コサイン類似度（0～SCALE）
 */

/**
 * 2次元配列を1次元にフラット化
 */
template Flatten2D(ROWS, COLS) {
    signal input matrix[ROWS][COLS];
    signal output flattened[ROWS * COLS];

    var idx = 0;
    for (var i = 0; i < ROWS; i++) {
        for (var j = 0; j < COLS; j++) {
            flattened[idx] <== matrix[i][j];
            idx++;
        }
    }
}

/**
 * ベクトルノルムの二乗を計算
 */
template VectorNormSquared(N) {
    signal input vector[N];
    signal output normSquared;

    signal squares[N];
    signal accumulator[N];

    for (var i = 0; i < N; i++) {
        squares[i] <== vector[i] * vector[i];

        if (i == 0) {
            accumulator[i] <== squares[i];
        } else {
            accumulator[i] <== accumulator[i-1] + squares[i];
        }
    }

    normSquared <== accumulator[N-1];
}

/**
 * 内積計算
 */
template DotProduct(N) {
    signal input vectorA[N];
    signal input vectorB[N];
    signal output dotProduct;

    signal products[N];
    signal accumulator[N];

    for (var i = 0; i < N; i++) {
        products[i] <== vectorA[i] * vectorB[i];

        if (i == 0) {
            accumulator[i] <== products[i];
        } else {
            accumulator[i] <== accumulator[i-1] + products[i];
        }
    }

    dotProduct <== accumulator[N-1];
}

/**
 * サブキャリア毎のコサイン類似度計算
 *
 * dotProduct * SCALE を similarity として出力（正規化は外部で実施）
 */
template SubcarrierCosine(NUM_FREQ_POINTS, SCALE) {
    signal input ref[NUM_FREQ_POINTS];
    signal input cand[NUM_FREQ_POINTS];

    signal output similarity;  // dotProduct * SCALE
    signal output dotProduct;
    signal output isValid;

    // ノルム計算
    component normCalcA = VectorNormSquared(NUM_FREQ_POINTS);
    component normCalcB = VectorNormSquared(NUM_FREQ_POINTS);
    for (var i = 0; i < NUM_FREQ_POINTS; i++) {
        normCalcA.vector[i] <== ref[i];
        normCalcB.vector[i] <== cand[i];
    }

    // 内積
    component dotCalc = DotProduct(NUM_FREQ_POINTS);
    for (var j = 0; j < NUM_FREQ_POINTS; j++) {
        dotCalc.vectorA[j] <== ref[j];
        dotCalc.vectorB[j] <== cand[j];
    }
    dotProduct <== dotCalc.dotProduct;

    // ゼロベクトルチェック
    component normACheck = GreaterThan(128);
    normACheck.in[0] <== normCalcA.normSquared;
    normACheck.in[1] <== 0;

    component normBCheck = GreaterThan(128);
    normBCheck.in[0] <== normCalcB.normSquared;
    normBCheck.in[1] <== 0;

    isValid <== normACheck.out * normBCheck.out;

    // similarity = dotProduct * SCALE (ゼロベクトルなら 0)
    similarity <== dotProduct * SCALE * isValid;
}

/**
 * メイン回路インスタンス
 *
 * パラメータ設定:
 * - NUM_FREQ_POINTS: 25 (呼吸周波数帯域 0.15～0.4Hz、0.01Hz刻み)
 * - NUM_SUBCARRIERS: 245 (サブキャリア数)
 * - SCALE: 10000 (固定小数点スケール)
 *
 * 総次元数: 25 × 245 = 6125
 */
template CosineSimilarityFullData(NUM_FREQ_POINTS, NUM_SUBCARRIERS, SCALE) {
    signal input referenceMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS];
    signal input candidateMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS];

    signal output similarities[NUM_SUBCARRIERS];
    signal output minSimilarity;
    signal output minIndex;

    // サブキャリアごとの計算
    signal minSim[NUM_SUBCARRIERS];
    signal minIdx[NUM_SUBCARRIERS];

    for (var sc = 0; sc < NUM_SUBCARRIERS; sc++) {
        component subcos = SubcarrierCosine(NUM_FREQ_POINTS, SCALE);
        for (var f = 0; f < NUM_FREQ_POINTS; f++) {
            subcos.ref[f] <== referenceMatrix[f][sc];
            subcos.cand[f] <== candidateMatrix[f][sc];
        }
        similarities[sc] <== subcos.similarity;

        if (sc == 0) {
            minSim[0] <== similarities[0];
            minIdx[0] <== 0;
        } else {
            component lt = LessThan();
            lt.in[0] <== similarities[sc];
            lt.in[1] <== minSim[sc - 1];

            // min similarity
            minSim[sc] <== lt.out * similarities[sc] + (1 - lt.out) * minSim[sc - 1];
            // min index
            minIdx[sc] <== lt.out * sc + (1 - lt.out) * minIdx[sc - 1];
        }
    }

    minSimilarity <== minSim[NUM_SUBCARRIERS - 1];
    minIndex <== minIdx[NUM_SUBCARRIERS - 1];
}

component main {public [referenceMatrix, candidateMatrix, similarities, minSimilarity, minIndex]} = CosineSimilarityFullData(25, 245, 10000);
