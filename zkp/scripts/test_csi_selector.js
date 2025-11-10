/**
 * CSIサブキャリア選択回路のテストスクリプト
 *
 * コサイン類似度計算と witness 生成のテスト
 */

const fs = require('fs');
const path = require('path');

// 固定小数点スケール
const SCALE = 10000;

/**
 * ベクトルのノルムを計算
 * ||V|| = √(Σ Vi²)
 */
function calculateNorm(vector) {
    const sumSquares = vector.reduce((sum, val) => sum + val * val, 0);
    return Math.sqrt(sumSquares);
}

/**
 * 内積を計算
 * A·B = Σ(Ai × Bi)
 */
function calculateDotProduct(vectorA, vectorB) {
    if (vectorA.length !== vectorB.length) {
        throw new Error('Vector dimensions must match');
    }
    return vectorA.reduce((sum, val, i) => sum + val * vectorB[i], 0);
}

/**
 * コサイン類似度を計算
 * cos_sim(A, B) = (A·B) / (||A|| × ||B||)
 */
function calculateCosineSimilarity(vectorA, vectorB) {
    const dotProduct = calculateDotProduct(vectorA, vectorB);
    const normA = calculateNorm(vectorA);
    const normB = calculateNorm(vectorB);

    if (normA === 0 || normB === 0) {
        return 0;
    }

    return dotProduct / (normA * normB);
}

/**
 * 浮動小数点数を固定小数点整数に変換
 */
function toFixedPoint(value, scale = SCALE) {
    return Math.round(value * scale);
}

/**
 * 固定小数点整数を浮動小数点数に変換
 */
function fromFixedPoint(value, scale = SCALE) {
    return value / scale;
}

/**
 * テストケース1: 同一ベクトル (類似度 = 1.0)
 */
function testCase1() {
    console.log('\n===== テストケース1: 同一ベクトル =====');

    const vectorA = [1.0, 0.5, 0.3, 0.2];
    const vectorB = [1.0, 0.5, 0.3, 0.2];

    const similarity = calculateCosineSimilarity(vectorA, vectorB);
    console.log(`期待される類似度: ${similarity.toFixed(6)}`);

    // 固定小数点変換
    const vectorA_fp = vectorA.map(v => toFixedPoint(v));
    const vectorB_fp = vectorB.map(v => toFixedPoint(v));

    const normA = calculateNorm(vectorA_fp);
    const normB = calculateNorm(vectorB_fp);
    const dotProduct = calculateDotProduct(vectorA_fp, vectorB_fp);

    const similarity_fp = Math.round((dotProduct * SCALE) / (normA * normB));

    console.log(`固定小数点計算結果: ${fromFixedPoint(similarity_fp).toFixed(6)}`);
    console.log(`Witness入力:`);
    console.log(`  vectorA: [${vectorA_fp.join(', ')}]`);
    console.log(`  vectorB: [${vectorB_fp.join(', ')}]`);
    console.log(`  normA: ${Math.round(normA)}`);
    console.log(`  normB: ${Math.round(normB)}`);
    console.log(`  similarity: ${similarity_fp}`);

    return {
        vectorA: vectorA_fp,
        vectorB: vectorB_fp,
        normA: Math.round(normA),
        normB: Math.round(normB),
        similarity: similarity_fp
    };
}

/**
 * テストケース2: 直交ベクトル (類似度 = 0.0)
 */
function testCase2() {
    console.log('\n===== テストケース2: 直交ベクトル =====');

    const vectorA = [1.0, 0.0, 0.0, 0.0];
    const vectorB = [0.0, 1.0, 0.0, 0.0];

    const similarity = calculateCosineSimilarity(vectorA, vectorB);
    console.log(`期待される類似度: ${similarity.toFixed(6)}`);

    // 固定小数点変換
    const vectorA_fp = vectorA.map(v => toFixedPoint(v));
    const vectorB_fp = vectorB.map(v => toFixedPoint(v));

    const normA = calculateNorm(vectorA_fp);
    const normB = calculateNorm(vectorB_fp);
    const dotProduct = calculateDotProduct(vectorA_fp, vectorB_fp);

    const similarity_fp = dotProduct === 0 ? 0 : Math.round((dotProduct * SCALE) / (normA * normB));

    console.log(`固定小数点計算結果: ${fromFixedPoint(similarity_fp).toFixed(6)}`);
    console.log(`Witness入力:`);
    console.log(`  vectorA: [${vectorA_fp.join(', ')}]`);
    console.log(`  vectorB: [${vectorB_fp.join(', ')}]`);
    console.log(`  normA: ${Math.round(normA)}`);
    console.log(`  normB: ${Math.round(normB)}`);
    console.log(`  similarity: ${similarity_fp}`);

    return {
        vectorA: vectorA_fp,
        vectorB: vectorB_fp,
        normA: Math.round(normA),
        normB: Math.round(normB),
        similarity: similarity_fp
    };
}

/**
 * テストケース3: CSI実データ風のベクトル (高い類似度)
 */
function testCase3() {
    console.log('\n===== テストケース3: CSI実データ風 (高類似度) =====');

    // CSI振幅データをシミュレート (正規化済み)
    const vectorA = [0.85, 0.62, 0.48, 0.31];
    const vectorB = [0.82, 0.65, 0.45, 0.33];

    const similarity = calculateCosineSimilarity(vectorA, vectorB);
    console.log(`期待される類似度: ${similarity.toFixed(6)}`);

    // 固定小数点変換
    const vectorA_fp = vectorA.map(v => toFixedPoint(v));
    const vectorB_fp = vectorB.map(v => toFixedPoint(v));

    const normA = calculateNorm(vectorA_fp);
    const normB = calculateNorm(vectorB_fp);
    const dotProduct = calculateDotProduct(vectorA_fp, vectorB_fp);

    const similarity_fp = Math.round((dotProduct * SCALE) / (normA * normB));

    console.log(`固定小数点計算結果: ${fromFixedPoint(similarity_fp).toFixed(6)}`);
    console.log(`閾値判定 (0.7): ${similarity_fp >= 7000 ? '✓ 合格' : '✗ 不合格'}`);

    return {
        vectorA: vectorA_fp,
        vectorB: vectorB_fp,
        normA: Math.round(normA),
        normB: Math.round(normB),
        similarity: similarity_fp
    };
}

/**
 * テストケース4: サブキャリア選択 (2候補から選択)
 */
function testCase4() {
    console.log('\n===== テストケース4: サブキャリア選択 =====');

    const reference = [0.85, 0.62, 0.48, 0.31];
    const candidate1 = [0.82, 0.65, 0.45, 0.33];  // 高類似度
    const candidate2 = [0.45, 0.30, 0.85, 0.60];  // 低類似度

    const sim1 = calculateCosineSimilarity(reference, candidate1);
    const sim2 = calculateCosineSimilarity(reference, candidate2);

    console.log(`候補1の類似度: ${sim1.toFixed(6)}`);
    console.log(`候補2の類似度: ${sim2.toFixed(6)}`);
    console.log(`選択されるべき候補: ${sim1 > sim2 ? '候補1' : '候補2'}`);

    // 固定小数点変換
    const reference_fp = reference.map(v => toFixedPoint(v));
    const candidate1_fp = candidate1.map(v => toFixedPoint(v));
    const candidate2_fp = candidate2.map(v => toFixedPoint(v));

    const refNorm = calculateNorm(reference_fp);
    const norm1 = calculateNorm(candidate1_fp);
    const norm2 = calculateNorm(candidate2_fp);

    const dot1 = calculateDotProduct(reference_fp, candidate1_fp);
    const dot2 = calculateDotProduct(reference_fp, candidate2_fp);

    const sim1_fp = Math.round((dot1 * SCALE) / (refNorm * norm1));
    const sim2_fp = Math.round((dot2 * SCALE) / (refNorm * norm2));

    console.log(`\n固定小数点計算結果:`);
    console.log(`  候補1類似度: ${fromFixedPoint(sim1_fp).toFixed(6)}`);
    console.log(`  候補2類似度: ${fromFixedPoint(sim2_fp).toFixed(6)}`);
    console.log(`  選択インデックス: ${sim1_fp > sim2_fp ? 0 : 1}`);

    // Witness データ生成
    const witness = {
        reference: reference_fp,
        candidates: [candidate1_fp, candidate2_fp],
        referenceNorm: Math.round(refNorm),
        candidateNorms: [Math.round(norm1), Math.round(norm2)],
        similarities: [sim1_fp, sim2_fp]
    };

    return witness;
}

/**
 * Witness JSONファイルを生成
 */
function generateWitnessJSON(witness, filename = 'csi_selector_witness.json') {
    const outputPath = path.join(__dirname, '..', filename);
    fs.writeFileSync(outputPath, JSON.stringify(witness, null, 2));
    console.log(`\nWitness JSONファイルを生成: ${outputPath}`);
}

// メイン実行
function main() {
    console.log('==========================================');
    console.log('CSIサブキャリア選択回路テスト');
    console.log('==========================================');

    try {
        testCase1();
        testCase2();
        testCase3();
        const witness = testCase4();

        // Witness JSONファイル生成
        generateWitnessJSON(witness);

        console.log('\n==========================================');
        console.log('全テスト完了 ✓');
        console.log('==========================================');
    } catch (error) {
        console.error('\nエラー発生:', error);
        process.exit(1);
    }
}

// スクリプト実行
if (require.main === module) {
    main();
}

module.exports = {
    calculateNorm,
    calculateDotProduct,
    calculateCosineSimilarity,
    toFixedPoint,
    fromFixedPoint
};
