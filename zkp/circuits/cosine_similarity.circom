pragma circom 2.0.0;

include "../node_modules/circomlib/circuits/comparators.circom";

/**
 * CSIサブキャリア選択のためのコサイン類似度計算回路
 *
 * 固定小数点演算によるコサイン類似度計算
 * スケーリングファクター: 10^3 (1000) - 計算効率とオーバーフロー防止のバランス
 *
 * 正規化されたコサイン類似度:
 * cos_sim(A, B) = (A·B) / (||A|| × ||B||)
 *
 * Circomの制約:
 * - 除算演算は witness による検証が必要
 * - 平方根は Newton法などの反復アルゴリズムで近似
 *
 * 入力:
 *   - vectorA[N]: 参照CSIサブキャリアベクトル (固定小数点 × 10^3)
 *   - vectorB[N]: 比較対象CSIサブキャリアベクトル (固定小数点 × 10^3)
 *   - normA: ベクトルAのノルム (事前計算、固定小数点 × 10^3)
 *   - normB: ベクトルBのノルム (事前計算、固定小数点 × 10^3)
 *   - threshold: 類似度閾値 (固定小数点 × 10^3, 例: 700 = 0.7)
 *
 * 出力:
 *   - similarity: コサイン類似度 (0〜1000, 0.000〜1.000を表現)
 *   - isHighSimilarity: 類似度が閾値以上の場合1
 */
template CosineSimilarity(N) {
    // 入力信号
    signal input vectorA[N];
    signal input vectorB[N];
    signal input normA;          // ||A|| (事前計算)
    signal input normB;          // ||B|| (事前計算)
    signal input threshold;      // 類似度閾値 (固定小数点 × 10^3)

    // 出力信号
    signal output similarity;
    signal output isHighSimilarity;

    // 内部信号
    signal dotProduct;           // A·B (内積)

    // 中間計算用
    signal products[N];          // Ai × Bi

    // ===== ステップ1: 内積計算 (A·B) =====
    signal dotProductAccum[N];
    for (var i = 0; i < N; i++) {
        products[i] <== vectorA[i] * vectorB[i];

        if (i == 0) {
            dotProductAccum[i] <== products[i];
        } else {
            dotProductAccum[i] <== dotProductAccum[i-1] + products[i];
        }
    }
    dotProduct <== dotProductAccum[N-1];

    // ===== ステップ2: コサイン類似度計算 =====
    // cos_sim = (A·B) / (||A|| × ||B||)
    // 固定小数点補正: (dotProduct × SCALE) / (normA × normB)
    // SCALE = 1000 (10^3)

    signal denominator;
    denominator <== normA * normB;

    // ゼロ除算チェック
    component denominatorCheck = GreaterThan(252);
    denominatorCheck.in[0] <== denominator;
    denominatorCheck.in[1] <== 0;

    // 分子の計算 (スケール調整)
    // dotProduct は既に 10^6 スケール (vectorA × vectorB)
    // normA, normB は 10^3 スケール
    // denominator = normA × normB は 10^6 スケール
    // similarity = (dotProduct × 10^3) / denominator で 10^3 スケールに正規化

    signal numerator;
    numerator <== dotProduct * 1000;

    // 除算の検証
    // similarity × denominator === numerator を制約として表現
    signal similarity_raw;
    signal verification;
    verification <== similarity_raw * denominator;
    verification === numerator;

    similarity <== similarity_raw;

    // ===== ステップ3: 閾値判定 =====
    component thresholdCheck = GreaterEqThan(32);
    thresholdCheck.in[0] <== similarity;
    thresholdCheck.in[1] <== threshold;
    isHighSimilarity <== thresholdCheck.out;
}

/**
 * CSIサブキャリア選択回路
 *
 * 複数のサブキャリアペアから最も類似度の高いものを選択
 */
template SubcarrierSelector(N, M) {
    // N: ベクトル次元, M: サブキャリアペア数

    signal input reference[N];        // 参照ベクトル
    signal input candidates[M][N];    // 候補ベクトル群
    signal input threshold;           // 選択閾値

    signal output selectedIndex;      // 選択されたインデックス
    signal output maxSimilarity;      // 最大類似度
    signal output isValid;            // 閾値以上の候補が存在する場合1

    // 各候補の類似度計算
    component cosSimCalc[M];
    signal similarities[M];
    signal validFlags[M];

    for (var i = 0; i < M; i++) {
        cosSimCalc[i] = CosineSimilarity(N);

        for (var j = 0; j < N; j++) {
            cosSimCalc[i].vectorA[j] <== reference[j];
            cosSimCalc[i].vectorB[j] <== candidates[i][j];
        }
        cosSimCalc[i].threshold <== threshold;

        similarities[i] <== cosSimCalc[i].similarity;
        validFlags[i] <== cosSimCalc[i].isHighSimilarity;
    }

    // 最大値検索 (簡易実装: 2候補の場合)
    // 実際の実装では、M個の候補から最大値を見つけるロジックが必要
    // ここではM=2の場合の例を示す

    // TODO: 一般的なM個の最大値検索アルゴリズムの実装
    // 現在は2候補の比較のみ
    component maxComparator = GreaterThan(252);
    maxComparator.in[0] <== similarities[0];
    maxComparator.in[1] <== similarities[1];

    signal indexSelector;
    indexSelector <== maxComparator.out;
    selectedIndex <== indexSelector;  // 0 or 1

    maxSimilarity <== similarities[0] * (1 - indexSelector) + similarities[1] * indexSelector;
    isValid <== validFlags[0] + validFlags[1];  // いずれかが閾値以上なら > 0
}

// サンプル: 4次元ベクトルでのコサイン類似度計算
component main {public [vectorA, vectorB, threshold]} = CosineSimilarity(4);
