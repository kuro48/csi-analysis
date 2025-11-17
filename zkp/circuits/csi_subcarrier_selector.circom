pragma circom 2.0.0;

include "../node_modules/circomlib/circuits/comparators.circom";

/**
 * CSIサブキャリア選択のためのコサイン類似度計算回路（実用版）
 *
 * Circomの制約を考慮した実装:
 * - 除算は witness 側で計算し、回路内で検証
 * - 固定小数点演算でスケール管理
 * - オーバーフロー防止のため適切なビット幅設定
 *
 * 固定小数点スケール: 10^4 (10000)
 * - 入力ベクトル値: -10000 〜 10000 (実数 -1.0 〜 1.0)
 * - 類似度出力: 0 〜 10000 (実数 0.0 〜 1.0)
 *
 * アプローチ:
 * 1. 内積計算は回路内で実施
 * 2. ノルム計算も回路内で実施
 * 3. 除算結果(similarity)は witness から入力し、検証制約で確認
 * 4. 閾値判定で有効なサブキャリアを選択
 */

template VectorNorm(N) {
    signal input vector[N];
    signal output normSquared;    // ノルムの二乗を出力 (平方根は witness で計算)

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
 * 内積計算テンプレート
 * A·B = Σ(Ai × Bi)
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
 * コサイン類似度計算 (witness 検証版)
 *
 * witness側で以下を計算:
 * - normA = sqrt(normA_squared)
 * - normB = sqrt(normB_squared)
 * - similarity = (dotProduct × SCALE) / (normA × normB)
 *
 * 回路側で検証:
 * - normA² が正しいか
 * - normB² が正しいか
 * - dotProduct が正しいか
 * - similarity が正しいか (similarity × normA × normB ≈ dotProduct × SCALE)
 */
template CosineSimilarityVerified(N, SCALE) {
    signal input vectorA[N];
    signal input vectorB[N];

    // Witness から提供される値
    signal input normA;              // ||A|| (witness計算)
    signal input normB;              // ||B|| (witness計算)
    signal input similarity;         // cos_sim(A,B) (witness計算)

    signal output normA_squared;     // 検証用
    signal output normB_squared;     // 検証用
    signal output dotProduct;        // 検証用
    signal output isValid;           // ゼロベクトルでない場合1

    // ===== ステップ1: ノルムの二乗を計算 =====
    component normCalcA = VectorNorm(N);
    component normCalcB = VectorNorm(N);

    for (var i = 0; i < N; i++) {
        normCalcA.vector[i] <== vectorA[i];
        normCalcB.vector[i] <== vectorB[i];
    }

    normA_squared <== normCalcA.normSquared;
    normB_squared <== normCalcB.normSquared;

    // ===== ステップ2: ノルムの検証 =====
    // normA² = witness で渡された normA の二乗
    signal normA_squared_verify;
    normA_squared_verify <== normA * normA;
    normA_squared_verify === normA_squared;

    signal normB_squared_verify;
    normB_squared_verify <== normB * normB;
    normB_squared_verify === normB_squared;

    // ===== ステップ3: 内積計算 =====
    component dotCalc = DotProduct(N);
    for (var i = 0; i < N; i++) {
        dotCalc.vectorA[i] <== vectorA[i];
        dotCalc.vectorB[i] <== vectorB[i];
    }
    dotProduct <== dotCalc.dotProduct;

    // ===== ステップ4: 類似度の検証 =====
    // similarity × normA × normB ≈ dotProduct × SCALE
    // (近似: 整数除算による誤差を許容)
    signal lhs;  // left-hand side
    signal rhs;  // right-hand side
    signal temp;  // 中間変数

    // 二次制約に分解: temp = similarity * normA, then lhs = temp * normB
    temp <== similarity * normA;
    lhs <== temp * normB;
    rhs <== dotProduct * SCALE;

    // 検証: lhs と rhs の差が許容範囲内
    // 簡易版: lhs === rhs (厳密な検証)
    lhs === rhs;

    // ===== ステップ5: ゼロベクトルチェック =====
    component normACheck = GreaterThan(64);
    normACheck.in[0] <== normA;
    normACheck.in[1] <== 0;

    component normBCheck = GreaterThan(64);
    normBCheck.in[0] <== normB;
    normBCheck.in[1] <== 0;

    isValid <== normACheck.out * normBCheck.out;
}

/**
 * CSIサブキャリア選択メイン回路
 *
 * 複数のサブキャリアペアから最も類似度の高いものを選択
 */
template CSISubcarrierSelector(N, M, SCALE, THRESHOLD) {
    // N: ベクトル次元数
    // M: サブキャリアペア候補数
    // SCALE: 固定小数点スケール (例: 10000)
    // THRESHOLD: 選択閾値 (例: 7000 = 0.7)

    signal input reference[N];           // 参照CSIベクトル
    signal input candidates[M][N];       // 候補CSIベクトル群

    // Witness から提供される計算済み値
    signal input candidateNorms[M];      // 各候補のノルム
    signal input similarities[M];        // 各候補の類似度
    signal input referenceNorm;          // 参照ベクトルのノルム

    signal output bestIndex;             // 最も類似度が低い候補のインデックス（ノイズの少ないサブキャリア）
    signal output bestSimilarity;        // 最小類似度
    signal output hasValidCandidate;     // 閾値以下の候補が存在する場合1

    // 各候補の類似度を検証
    component cosSimVerifiers[M];
    component thresholdCheck[M];
    signal validFlags[M];

    for (var i = 0; i < M; i++) {
        cosSimVerifiers[i] = CosineSimilarityVerified(N, SCALE);

        // 入力設定
        for (var j = 0; j < N; j++) {
            cosSimVerifiers[i].vectorA[j] <== reference[j];
            cosSimVerifiers[i].vectorB[j] <== candidates[i][j];
        }
        cosSimVerifiers[i].normA <== referenceNorm;
        cosSimVerifiers[i].normB <== candidateNorms[i];
        cosSimVerifiers[i].similarity <== similarities[i];

        // 閾値チェック（類似度が低い = ノイズが少ない）
        // 類似度が閾値以下であることを確認
        thresholdCheck[i] = LessEqThan(32);
        thresholdCheck[i].in[0] <== similarities[i];
        thresholdCheck[i].in[1] <== THRESHOLD;

        validFlags[i] <== thresholdCheck[i].out * cosSimVerifiers[i].isValid;
    }

    // 最小類似度のインデックスを見つける (M=2の簡易実装)
    // 類似性が低いものを選択（ノイズの少ないサブキャリア）
    component minFinder = LessThan(32);
    minFinder.in[0] <== similarities[0];
    minFinder.in[1] <== similarities[1];

    signal selectedIndex;
    // LessThan: similarities[0] < similarities[1] なら 1, そうでなければ 0
    // 目標: 類似度が低い方のインデックスを選択
    // - similarities[0] < similarities[1] (候補0の方が低い) → minFinder.out = 1 だが selectedIndex = 0 にすべき
    // - similarities[0] >= similarities[1] (候補1の方が低い) → minFinder.out = 0 だが selectedIndex = 1 にすべき
    // したがって反転が必要: selectedIndex = 1 - minFinder.out
    selectedIndex <== 1 - minFinder.out;

    bestIndex <== selectedIndex;

    // bestSimilarity の計算（二次制約を守る）
    signal inverseIndex;
    signal term1;
    signal term2;
    inverseIndex <== 1 - selectedIndex;
    term1 <== similarities[0] * inverseIndex;
    term2 <== similarities[1] * selectedIndex;
    bestSimilarity <== term1 + term2;

    // 有効な候補が存在するかチェック
    signal validSum;
    validSum <== validFlags[0] + validFlags[1];

    component hasValid = GreaterThan(32);
    hasValid.in[0] <== validSum;
    hasValid.in[1] <== 0;

    hasValidCandidate <== hasValid.out;
}

// サンプルインスタンス: 4次元ベクトル、2候補、スケール10000、閾値7000(0.7)
component main {public [reference, candidates]} = CSISubcarrierSelector(4, 2, 10000, 7000);
