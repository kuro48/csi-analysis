#!/usr/bin/env node

/**
 * JavaScript直接計算で全サブキャリアのコサイン類似度を計算
 * 開発モード専用 - ZKPを使わずに高速に類似度を計算
 */

const fs = require('fs');
const path = require('path');

const NUM_FREQ_POINTS = 25;
const NUM_SUBCARRIERS = 245;

/**
 * サンプルCSIデータを生成
 */
function generateSampleCSIData() {
    const referenceMatrix = [];
    const candidateMatrix = [];

    for (let f = 0; f < NUM_FREQ_POINTS; f++) {
        const refRow = [];
        const candRow = [];
        for (let sc = 0; sc < NUM_SUBCARRIERS; sc++) {
            // ベースCSI: 正弦波パターン
            const baseValue = Math.sin((f + sc) * 0.1) * 1000 + 1000;
            refRow.push(Math.round(baseValue));

            // 候補CSI: サブキャリアごとに異なるノイズを追加
            const noiseLevel = (sc % 50) * 10;
            const noise = (Math.random() - 0.5) * noiseLevel;
            candRow.push(Math.round(baseValue + noise));
        }
        referenceMatrix.push(refRow);
        candidateMatrix.push(candRow);
    }

    return { referenceMatrix, candidateMatrix };
}

/**
 * CSIデータをファイルから読み込み
 */
function loadCSIDataFromFile(filePath) {
    try {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        return {
            referenceMatrix: data.referenceMatrix || data.reference_matrix,
            candidateMatrix: data.candidateMatrix || data.candidate_matrix
        };
    } catch (error) {
        console.error(`Failed to load CSI data from ${filePath}:`, error.message);
        return null;
    }
}

/**
 * コサイン類似度を計算
 */
function calculateCosineSimilarity(refVector, candVector) {
    let dotProduct = 0;
    let normRef = 0;
    let normCand = 0;

    for (let i = 0; i < refVector.length; i++) {
        dotProduct += refVector[i] * candVector[i];
        normRef += refVector[i] * refVector[i];
        normCand += candVector[i] * candVector[i];
    }

    normRef = Math.sqrt(normRef);
    normCand = Math.sqrt(normCand);

    if (normRef === 0 || normCand === 0) {
        return 0;
    }

    return dotProduct / (normRef * normCand);
}

/**
 * 全サブキャリアの類似度を計算
 */
function calculateAllSimilarities(referenceMatrix, candidateMatrix) {
    const similarities = [];
    const details = [];

    for (let sc = 0; sc < NUM_SUBCARRIERS; sc++) {
        const refVector = [];
        const candVector = [];

        for (let f = 0; f < NUM_FREQ_POINTS; f++) {
            refVector.push(referenceMatrix[f][sc]);
            candVector.push(candidateMatrix[f][sc]);
        }

        const similarity = calculateCosineSimilarity(refVector, candVector);
        similarities.push(similarity);

        // 詳細情報を保存
        let dotProduct = 0;
        let normRefSq = 0;
        let normCandSq = 0;
        for (let i = 0; i < refVector.length; i++) {
            dotProduct += refVector[i] * candVector[i];
            normRefSq += refVector[i] * refVector[i];
            normCandSq += candVector[i] * candVector[i];
        }

        details.push({
            subcarrier: sc,
            similarity: similarity,
            dotProduct: dotProduct,
            normRef: Math.sqrt(normRefSq),
            normCand: Math.sqrt(normCandSq)
        });
    }

    return { similarities, details };
}

/**
 * 上位N個の低類似度サブキャリアを取得
 */
function getTopNLowest(similarities, n = 5) {
    const indexed = similarities.map((sim, idx) => ({ index: idx, similarity: sim }));
    indexed.sort((a, b) => a.similarity - b.similarity);
    return indexed.slice(0, n);
}

/**
 * 上位N個の高類似度サブキャリアを取得
 */
function getTopNHighest(similarities, n = 5) {
    const indexed = similarities.map((sim, idx) => ({ index: idx, similarity: sim }));
    indexed.sort((a, b) => b.similarity - a.similarity);
    return indexed.slice(0, n);
}

/**
 * 統計情報を計算
 */
function calculateStatistics(similarities) {
    const mean = similarities.reduce((a, b) => a + b, 0) / similarities.length;
    const sorted = [...similarities].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];
    const min = sorted[0];
    const max = sorted[sorted.length - 1];

    const variance = similarities.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / similarities.length;
    const stdDev = Math.sqrt(variance);

    return { mean, median, min, max, stdDev };
}

function main() {
    console.log('📊 Calculating all subcarrier cosine similarities (JavaScript)...\n');

    // コマンドライン引数からファイルパスを取得
    const args = process.argv.slice(2);
    let referenceMatrix, candidateMatrix;

    if (args.length > 0 && fs.existsSync(args[0])) {
        console.log(`📂 Loading CSI data from: ${args[0]}`);
        const data = loadCSIDataFromFile(args[0]);
        if (!data) {
            console.error('Failed to load data. Using sample data instead.');
            const sample = generateSampleCSIData();
            referenceMatrix = sample.referenceMatrix;
            candidateMatrix = sample.candidateMatrix;
        } else {
            referenceMatrix = data.referenceMatrix;
            candidateMatrix = data.candidateMatrix;
        }
    } else {
        console.log('📊 Generating sample CSI data...');
        const sample = generateSampleCSIData();
        referenceMatrix = sample.referenceMatrix;
        candidateMatrix = sample.candidateMatrix;
    }

    console.log(`  Matrix dimensions: ${NUM_FREQ_POINTS} x ${NUM_SUBCARRIERS}\n`);

    // 類似度計算
    console.log('🔢 Calculating similarities...');
    const startTime = Date.now();
    const { similarities, details } = calculateAllSimilarities(referenceMatrix, candidateMatrix);
    const elapsedTime = Date.now() - startTime;
    console.log(`✅ Calculation completed in ${elapsedTime}ms\n`);

    // 統計情報
    const stats = calculateStatistics(similarities);
    console.log('📈 Statistics:');
    console.log(`  Mean:     ${stats.mean.toFixed(6)}`);
    console.log(`  Median:   ${stats.median.toFixed(6)}`);
    console.log(`  Std Dev:  ${stats.stdDev.toFixed(6)}`);
    console.log(`  Min:      ${stats.min.toFixed(6)}`);
    console.log(`  Max:      ${stats.max.toFixed(6)}\n`);

    // 上位5つの低類似度
    const topLowest = getTopNLowest(similarities, 5);
    console.log('📉 Top 5 Lowest Similarities:');
    topLowest.forEach((item, rank) => {
        const detail = details[item.index];
        console.log(
            `  ${rank + 1}. Subcarrier ${item.index.toString().padStart(3)}: ` +
            `${item.similarity.toFixed(6)} ` +
            `(dot=${detail.dotProduct.toFixed(2)}, norm_ref=${detail.normRef.toFixed(2)}, norm_cand=${detail.normCand.toFixed(2)})`
        );
    });

    // 上位5つの高類似度（参考）
    const topHighest = getTopNHighest(similarities, 5);
    console.log('\n📈 Top 5 Highest Similarities (for reference):');
    topHighest.forEach((item, rank) => {
        const detail = details[item.index];
        console.log(
            `  ${rank + 1}. Subcarrier ${item.index.toString().padStart(3)}: ` +
            `${item.similarity.toFixed(6)} ` +
            `(dot=${detail.dotProduct.toFixed(2)}, norm_ref=${detail.normRef.toFixed(2)}, norm_cand=${detail.normCand.toFixed(2)})`
        );
    });

    // 結果をファイルに保存
    const resultsDir = path.join(__dirname, '../results');
    if (!fs.existsSync(resultsDir)) {
        fs.mkdirSync(resultsDir, { recursive: true });
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const resultsFile = path.join(resultsDir, `js_similarities_${timestamp}.json`);

    const results = {
        timestamp: new Date().toISOString(),
        num_subcarriers: NUM_SUBCARRIERS,
        num_freq_points: NUM_FREQ_POINTS,
        calculation_time_ms: elapsedTime,
        statistics: stats,
        top_5_lowest: topLowest,
        top_5_highest: topHighest,
        all_similarities: similarities,
        all_details: details
    };

    fs.writeFileSync(resultsFile, JSON.stringify(results, null, 2));
    console.log(`\n💾 Results saved to: ${resultsFile}`);
}

main();
