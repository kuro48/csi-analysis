pragma circom 2.0.0;

include "../node_modules/circomlib/circuits/comparators.circom";
include "../node_modules/circomlib/circuits/multiplexers.circom";
include "../node_modules/circomlib/circuits/bitify.circom";

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
 * - similarities[NUM_SUBCARRIERS]: 各サブキャリアの similarity (dot * SCALE / (normA*normB) を近似)
 * - minSimilarity: 最小類似度
 * - minIndex: 最小類似度のサブキャリア index
 */

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
template InvSqrtApprox(iterations) {
    signal input x;
    signal input scale;
    signal output invSqrt; // 固定小数点 (scale) で 1/sqrt(x) を近似

    // 初期値: x がゼロの場合を避けるため、下限を設ける（非常に粗いが安全側）
    // 初期値 y0 = 1 (scale 表現) とする
    signal y[iterations + 1];
    y[0] <== scale; // 1.0 を scale で表現

    for (var i = 0; i < iterations; i++) {
        // Newton-Raphson: y_{n+1} = y_n * (1.5 - 0.5 * x * y_n^2)
        // ただし固定小数点なのでスケール調整
        // y_n^2 / scale でスケール戻し
        signal y2;
        y2 <== (y[i] * y[i]) / scale;

        signal xy2;
        xy2 <== (x * y2) / scale;

        signal half_xy2;
        half_xy2 <== xy2 / 2;

        signal term;
        term <== (3 * scale) / 2 - half_xy2; // 1.5*scale - 0.5*x*y^2

        signal y_next;
        y_next <== (y[i] * term) / scale;
        y[i + 1] <== y_next;
    }

    invSqrt <== y[iterations];
}

template SubcarrierCosine(NUM_FREQ_POINTS, SCALE, ITER) {
    signal input ref[NUM_FREQ_POINTS];
    signal input cand[NUM_FREQ_POINTS];

    signal output similarity;  // 近似 cos(sim) * SCALE
    signal output dotProduct;
    signal output normA;
    signal output normB;
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

    // 逆平方根近似
    component invSqrt = InvSqrtApprox(ITER);
    invSqrt.x <== normCalcA.normSquared * normCalcB.normSquared; // (normA^2)*(normB^2)
    invSqrt.scale <== SCALE;

    // cos ≈ dot / (normA*normB) = dot * invSqrt(normA^2*normB^2)
    signal cos_approx;
    cos_approx <== (dotProduct * invSqrt.invSqrt) / SCALE;

    similarity <== cos_approx * SCALE * isValid;
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
template CosineSimilarityFullData(NUM_FREQ_POINTS, NUM_SUBCARRIERS, SCALE, ITER) {
    signal input referenceMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS];
    signal input candidateMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS];

    signal output similarities[NUM_SUBCARRIERS];
    signal output minSimilarity;
    signal output minIndex;

    // サブキャリアごとの計算
    signal minSim[NUM_SUBCARRIERS];
    signal minIdx[NUM_SUBCARRIERS];

    for (var sc = 0; sc < NUM_SUBCARRIERS; sc++) {
        component subcos = SubcarrierCosine(NUM_FREQ_POINTS, SCALE, ITER);
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

component main {public [similarities, minSimilarity, minIndex]} = CosineSimilarityFullData(25, 245, 10000, 2);
