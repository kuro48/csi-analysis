#!/usr/bin/env node

/**
 * 64サブキャリア全てのコサイン類似度を計算
 *
 * 実際のFFTデータから近似的なPythagorean tripleを生成し、
 * 全サブキャリア間のコサイン類似度を計算します。
 */

const fs = require('fs');
const path = require('path');
const csv = require('csvtojson');

// ファイルパス設定
const DATA_DIR = path.join(__dirname, '../data');
const FFT_CSV_FILE = path.join(DATA_DIR, 'csi_fft_real.csv');
const OUTPUT_DIR = path.join(DATA_DIR, 'similarity_results');

// 出力ディレクトリ作成
if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

/**
 * 既知のPythagorean tripleリスト（スケール25以下）
 */
const PYTHAGOREAN_TRIPLES = [
    [3, 4, 5],
    [5, 12, 13],
    [8, 15, 17],
    [7, 24, 25],
    [20, 21, 29],
    [9, 12, 15],
    [12, 16, 20],
    [15, 20, 25],
    [6, 8, 10],
    [9, 40, 41],
    [12, 35, 37],
    [11, 60, 61],
    [13, 84, 85],
    [36, 77, 85]
];

/**
 * FFT CSVファイルからパワースペクトルデータを読み込み
 */
async function loadFFTDataFromCSV(csvPath) {
    console.log('📂 Loading FFT data from CSV...');
    console.log(`   File: ${csvPath}`);

    if (!fs.existsSync(csvPath)) {
        throw new Error(`CSV file not found: ${csvPath}`);
    }

    const jsonArray = await csv().fromFile(csvPath);

    console.log(`✅ Loaded ${jsonArray.length} subcarrier FFT results`);

    // 各サブキャリアのパワースペクトルを抽出
    const fftData = jsonArray.map(row => {
        const subcarrierId = parseInt(row.subcarrier_id);
        const peakFreq = parseFloat(row.peak_freq);
        const peakPower = parseFloat(row.peak_power);

        // 最初の4周波数ビンを抽出
        const powerBins = [];
        for (let i = 0; i < 4; i++) {
            const key = `power_bin_${i}`;
            if (row[key]) {
                powerBins.push(parseFloat(row[key]));
            }
        }

        return {
            subcarrierId,
            peakFreq,
            peakPower,
            powerBins
        };
    });

    console.log(`   Extracted power spectrum for first 4 frequency bins`);

    return fftData;
}

/**
 * 4次元ベクトルを近似的なPythagorean triple比率に変換
 *
 * アプローチ：
 * 1. データを正規化（最大値で割る）
 * 2. 既知のPythagorean tripleとの類似度を計算
 * 3. 最も近いパターンを選択し、スケーリング
 */
function convertToApproximatePythagoreanTriple(data, subcarrierId) {
    // ゼロベクトルの処理
    const maxVal = Math.max(...data.map(Math.abs));
    if (maxVal === 0 || !isFinite(maxVal)) {
        return {
            vector: [0, 0, 0, 0],
            norm: 0,
            originalData: data,
            method: 'zero_vector'
        };
    }

    // 正規化
    const normalized = data.map(v => v / maxVal);

    // 方法1: 既知のPythagorean tripleから最適なものを選択
    let bestMatch = null;
    let bestScore = -Infinity;

    for (const triple of PYTHAGOREAN_TRIPLES) {
        // 4次元に拡張（3次元 → 4次元）
        const patterns = [
            [triple[0], triple[1], 0, 0],
            [triple[0], 0, triple[1], 0],
            [0, triple[0], triple[1], 0],
            [triple[1], triple[0], 0, 0],
            [triple[1], 0, triple[0], 0],
            [0, triple[1], triple[0], 0]
        ];

        for (const pattern of patterns) {
            // パターンを正規化
            const patternMax = Math.max(...pattern.map(Math.abs));
            if (patternMax === 0) continue;
            const normalizedPattern = pattern.map(v => v / patternMax);

            // コサイン類似度（正規化ベクトル同士）
            const dotProduct = normalized.reduce((sum, val, idx) =>
                sum + val * normalizedPattern[idx], 0);
            const normData = Math.sqrt(normalized.reduce((sum, v) => sum + v * v, 0));
            const normPattern = Math.sqrt(normalizedPattern.reduce((sum, v) => sum + v * v, 0));
            const similarity = dotProduct / (normData * normPattern);

            if (similarity > bestScore) {
                bestScore = similarity;
                bestMatch = {
                    pattern: pattern,
                    triple: triple,
                    similarity: similarity
                };
            }
        }
    }

    if (!bestMatch) {
        // フォールバック: 単純な丸め
        const scaled = normalized.map(v => Math.round(v * 10));
        return {
            vector: scaled,
            norm: calculateNorm(scaled),
            originalData: data,
            method: 'fallback_rounding'
        };
    }

    // 最適なパターンをスケーリング
    // データの最大値とパターンの最大値の比率を計算
    const dataMax = Math.max(...data.map(Math.abs));
    const patternMax = Math.max(...bestMatch.pattern.map(Math.abs));
    const scale = Math.round(dataMax / (maxVal * patternMax) * 10);
    const scaledPattern = bestMatch.pattern.map(v => Math.round(v * Math.max(1, scale / 2)));

    return {
        vector: scaledPattern,
        norm: calculateNorm(scaledPattern),
        originalData: data,
        method: 'pythagorean_approximation',
        matchedTriple: bestMatch.triple,
        similarity: bestMatch.similarity
    };
}

/**
 * ベクトルノルムを計算
 */
function calculateNorm(vector) {
    const sumOfSquares = vector.reduce((sum, val) => sum + val * val, 0);
    return Math.round(Math.sqrt(sumOfSquares));
}

/**
 * コサイン類似度を計算（固定小数点）
 */
function calculateCosineSimilarity(vecA, vecB, scale = 10000) {
    const dotProduct = vecA.reduce((sum, val, idx) => sum + val * vecB[idx], 0);
    const normA = calculateNorm(vecA);
    const normB = calculateNorm(vecB);

    if (normA === 0 || normB === 0) {
        return {
            similarity: 0,
            normA: 0,
            normB: 0,
            dotProduct: 0,
            verificationError: 0
        };
    }

    const similarity = Math.round((dotProduct * scale) / (normA * normB));

    // 検証式の誤差をチェック
    const lhs = similarity * normA * normB;
    const rhs = dotProduct * scale;
    const verificationError = Math.abs(lhs - rhs);

    return {
        similarity,
        normA,
        normB,
        dotProduct,
        verificationError
    };
}

/**
 * 全サブキャリアをPythagorean triple近似に変換
 */
function convertAllSubcarriers(fftData) {
    console.log('\n📊 Converting all 64 subcarriers to approximate Pythagorean triples...');

    const converted = fftData.map((sc, idx) => {
        const result = convertToApproximatePythagoreanTriple(sc.powerBins, sc.subcarrierId);

        if (idx < 5 || idx === fftData.length - 1) {
            console.log(`   SC ${sc.subcarrierId}: ${JSON.stringify(result.vector)} (norm=${result.norm}, method=${result.method})`);
        } else if (idx === 5) {
            console.log(`   ...`);
        }

        return {
            subcarrierId: sc.subcarrierId,
            ...result
        };
    });

    console.log(`✅ Converted ${converted.length} subcarriers`);

    return converted;
}

/**
 * 全サブキャリア間のコサイン類似度マトリックスを計算
 */
function calculateSimilarityMatrix(convertedSubcarriers) {
    console.log('\n📊 Calculating similarity matrix for all subcarrier pairs...');

    const n = convertedSubcarriers.length;
    const matrix = [];

    let totalComparisons = 0;
    let validComparisons = 0;

    for (let i = 0; i < n; i++) {
        const row = [];
        for (let j = 0; j < n; j++) {
            const scA = convertedSubcarriers[i];
            const scB = convertedSubcarriers[j];

            if (i === j) {
                // 自分自身との類似度は1.0 (10000)
                row.push({
                    similarity: 10000,
                    normA: scA.norm,
                    normB: scB.norm,
                    dotProduct: scA.norm * scA.norm,
                    verificationError: 0
                });
            } else {
                const result = calculateCosineSimilarity(scA.vector, scB.vector);
                row.push(result);

                totalComparisons++;
                if (result.verificationError === 0) {
                    validComparisons++;
                }
            }
        }
        matrix.push(row);

        if (i < 3 || i === n - 1) {
            const similarities = row.slice(0, 5).map(r => (r.similarity / 10000).toFixed(4));
            console.log(`   SC ${i}: [${similarities.join(', ')}, ...]`);
        } else if (i === 3) {
            console.log(`   ...`);
        }
    }

    console.log(`✅ Calculated ${totalComparisons} pairwise similarities`);
    console.log(`   Valid (zero verification error): ${validComparisons}/${totalComparisons} (${(validComparisons/totalComparisons*100).toFixed(1)}%)`);

    return matrix;
}

/**
 * 結果をCSVに保存
 */
async function saveSimilarityMatrixCSV(matrix, convertedSubcarriers) {
    const outputFile = path.join(OUTPUT_DIR, 'similarity_matrix.csv');

    // ヘッダー行
    const header = ['subcarrier_id', ...convertedSubcarriers.map(sc => `SC_${sc.subcarrierId}`)];
    const lines = [header.join(',')];

    // データ行
    for (let i = 0; i < matrix.length; i++) {
        const row = [convertedSubcarriers[i].subcarrierId];
        for (let j = 0; j < matrix[i].length; j++) {
            row.push((matrix[i][j].similarity / 10000).toFixed(4));
        }
        lines.push(row.join(','));
    }

    await fs.promises.writeFile(outputFile, lines.join('\n'));
    console.log(`\n💾 Similarity matrix saved: ${outputFile}`);
}

/**
 * 統計情報を保存
 */
async function saveStatistics(matrix, convertedSubcarriers) {
    const outputFile = path.join(OUTPUT_DIR, 'similarity_statistics.json');

    // 全類似度値を収集（対角成分を除く）
    const allSimilarities = [];
    for (let i = 0; i < matrix.length; i++) {
        for (let j = 0; j < matrix[i].length; j++) {
            if (i !== j) {
                allSimilarities.push(matrix[i][j].similarity / 10000);
            }
        }
    }

    allSimilarities.sort((a, b) => a - b);

    const stats = {
        num_subcarriers: convertedSubcarriers.length,
        total_comparisons: allSimilarities.length,
        similarity_range: {
            min: allSimilarities[0],
            max: allSimilarities[allSimilarities.length - 1],
            mean: allSimilarities.reduce((sum, v) => sum + v, 0) / allSimilarities.length,
            median: allSimilarities[Math.floor(allSimilarities.length / 2)]
        },
        top_10_pairs: []
    };

    // Top 10の類似度ペアを抽出
    const pairs = [];
    for (let i = 0; i < matrix.length; i++) {
        for (let j = i + 1; j < matrix[i].length; j++) {
            pairs.push({
                scA: convertedSubcarriers[i].subcarrierId,
                scB: convertedSubcarriers[j].subcarrierId,
                similarity: matrix[i][j].similarity / 10000,
                verificationError: matrix[i][j].verificationError
            });
        }
    }

    pairs.sort((a, b) => b.similarity - a.similarity);
    stats.top_10_pairs = pairs.slice(0, 10);

    await fs.promises.writeFile(outputFile, JSON.stringify(stats, null, 2));
    console.log(`💾 Statistics saved: ${outputFile}`);
}

/**
 * 変換されたベクトル情報を保存
 */
async function saveConvertedVectors(convertedSubcarriers) {
    const outputFile = path.join(OUTPUT_DIR, 'converted_vectors.json');

    const data = convertedSubcarriers.map(sc => ({
        subcarrierId: sc.subcarrierId,
        vector: sc.vector,
        norm: sc.norm,
        method: sc.method,
        matchedTriple: sc.matchedTriple,
        approximationQuality: sc.similarity
    }));

    await fs.promises.writeFile(outputFile, JSON.stringify(data, null, 2));
    console.log(`💾 Converted vectors saved: ${outputFile}`);
}

/**
 * メイン処理
 */
async function main() {
    try {
        console.log('🔐 Calculating cosine similarity for all 64 subcarriers...\n');

        // 1. FFT CSVファイルを読み込み
        const fftData = await loadFFTDataFromCSV(FFT_CSV_FILE);

        // 2. 全サブキャリアをPythagorean triple近似に変換
        const convertedSubcarriers = convertAllSubcarriers(fftData);

        // 3. 類似度マトリックスを計算
        const similarityMatrix = calculateSimilarityMatrix(convertedSubcarriers);

        // 4. 結果を保存
        await saveSimilarityMatrixCSV(similarityMatrix, convertedSubcarriers);
        await saveStatistics(similarityMatrix, convertedSubcarriers);
        await saveConvertedVectors(convertedSubcarriers);

        console.log('\n✅ All operations successful!');
        console.log(`\nResults saved in: ${OUTPUT_DIR}/`);
        console.log('  - similarity_matrix.csv: 64x64 similarity matrix');
        console.log('  - similarity_statistics.json: Statistical summary');
        console.log('  - converted_vectors.json: Pythagorean triple approximations');

    } catch (error) {
        console.error('\n❌ Error:', error.message);
        console.error(error.stack);
        process.exit(1);
    }
}

// スクリプト実行
main();
