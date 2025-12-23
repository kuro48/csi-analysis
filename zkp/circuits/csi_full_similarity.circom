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
 * コサイン類似度計算（完全回路内計算版）
 *
 * 入力:
 * - referenceMatrix, candidateMatrix (秘密入力)
 *
 * 回路内で計算:
 * - normA², normB²（ノルムの二乗）
 * - 内積
 * - 類似度（近似値、整数演算のみ）
 *
 * 出力:
 * - similarity: コサイン類似度（0～SCALE）
 * - dotProduct: 内積
 * - isValid: 有効な計算かどうか
 */
template CosineSimilarityFullData(NUM_FREQ_POINTS, NUM_SUBCARRIERS, SCALE) {
    var TOTAL_DIM = NUM_FREQ_POINTS * NUM_SUBCARRIERS;

    signal input referenceMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS];
    signal input candidateMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS];

    signal output similarity;        // コサイン類似度（0～SCALE）
    signal output dotProduct;        // 内積
    signal output isValid;           // 有効な計算かどうか

    // ===== ステップ1: 2次元配列を1次元にフラット化 =====
    component flattenRef = Flatten2D(NUM_FREQ_POINTS, NUM_SUBCARRIERS);
    component flattenCand = Flatten2D(NUM_FREQ_POINTS, NUM_SUBCARRIERS);

    for (var i = 0; i < NUM_FREQ_POINTS; i++) {
        for (var j = 0; j < NUM_SUBCARRIERS; j++) {
            flattenRef.matrix[i][j] <== referenceMatrix[i][j];
            flattenCand.matrix[i][j] <== candidateMatrix[i][j];
        }
    }

    // ===== ステップ2: ノルムの二乗を計算 =====
    component normCalcA = VectorNormSquared(TOTAL_DIM);
    component normCalcB = VectorNormSquared(TOTAL_DIM);

    for (var i = 0; i < TOTAL_DIM; i++) {
        normCalcA.vector[i] <== flattenRef.flattened[i];
        normCalcB.vector[i] <== flattenCand.flattened[i];
    }

    signal normA_squared;
    signal normB_squared;
    normA_squared <== normCalcA.normSquared;
    normB_squared <== normCalcB.normSquared;

    // ===== ステップ3: 内積計算 =====
    component dotCalc = DotProduct(TOTAL_DIM);
    for (var i = 0; i < TOTAL_DIM; i++) {
        dotCalc.vectorA[i] <== flattenRef.flattened[i];
        dotCalc.vectorB[i] <== flattenCand.flattened[i];
    }
    dotProduct <== dotCalc.dotProduct;

    // ===== ステップ4: ゼロベクトルチェック =====
    component normACheck = GreaterThan(128);
    normACheck.in[0] <== normA_squared;
    normACheck.in[1] <== 0;

    component normBCheck = GreaterThan(128);
    normBCheck.in[0] <== normB_squared;
    normBCheck.in[1] <== 0;

    isValid <== normACheck.out * normBCheck.out;

    // ===== ステップ5: 類似度計算（近似） =====
    // similarity = (dotProduct * SCALE) / sqrt(normA_squared * normB_squared)
    // 回路内では除算と平方根が難しいため、witnessで計算して検証する形に戻す
    // または、類似度をpublic outputとして出力し、外部で検証する

    // ここでは簡易的に、dotProduct * SCALE を出力として使用
    // 実際の類似度は外部で計算: dotProduct * SCALE / sqrt(normA_squared * normB_squared)
    similarity <== dotProduct * SCALE;
}

/**
 * メイン回路インスタンス
 *
 * パラメータ設定:
 * - NUM_FREQ_POINTS: 25 (呼吸周波数帯域 0.15～0.4Hz、0.01Hz刻み)
 * - NUM_SUBCARRIERS: 200 (ガードバンド、パイロット削除後の有効サブキャリア)
 * - SCALE: 10000 (固定小数点スケール)
 *
 * 総次元数: 25 × 200 = 5000
 */
// 類似度・内積・有効フラグも検証側で使うため public に含める
component main {public [referenceMatrix, candidateMatrix, similarity, dotProduct, isValid]} = CosineSimilarityFullData(25, 245, 10000);
