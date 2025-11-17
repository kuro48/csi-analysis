#!/usr/bin/env node

/**
 * FFT周波数成分CSVからZKP証明を生成（完全一致版）
 *
 * 実際のPCAPから抽出したCSIデータのFFT結果を使用して
 * 検証式が完全に成立する整数ベクトルを探索します。
 */

const fs = require('fs');
const path = require('path');
const snarkjs = require('snarkjs');
const csv = require('csvtojson');

// ファイルパス設定
const DATA_DIR = path.join(__dirname, '../data');
const BUILD_DIR = path.join(__dirname, '../build');
const KEYS_DIR = path.join(__dirname, '../keys');
const PROOFS_DIR = path.join(__dirname, '../proofs');

const FFT_CSV_FILE = path.join(DATA_DIR, 'csi_fft_real.csv');
const SCALE = 10000;

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

        return { subcarrierId, peakFreq, peakPower, powerBins };
    });

    return fftData;
}

/**
 * 検証式が完全に成立するベクトルペアを探索
 *
 * 条件:
 * similarity × normA × normB = dotProduct × SCALE (完全一致)
 * つまり: (dotProduct × SCALE) % (normA × normB) = 0
 */
function findExactMatchingVectors(refData, candData) {
    const maxVal = Math.max(...refData.map(Math.abs), ...candData.map(Math.abs));
    const normalized_ref = refData.map(v => v / maxVal);
    const normalized_cand = candData.map(v => v / maxVal);

    let bestMatch = null;
    let minError = Infinity;

    // スケール範囲を拡大して探索
    for (let scale_ref = 3; scale_ref <= 20; scale_ref++) {
        for (let scale_cand = 3; scale_cand <= 20; scale_cand++) {
            const vec_ref = normalized_ref.map(v => Math.round(v * scale_ref));
            const vec_cand = normalized_cand.map(v => Math.round(v * scale_cand));

            const normA = calculateNorm(vec_ref);
            const normB = calculateNorm(vec_cand);
            const dotProduct = calculateDotProduct(vec_ref, vec_cand);

            if (normA === 0 || normB === 0) continue;

            // 検証式の完全一致度を計算
            const numerator = dotProduct * SCALE;
            const denominator = normA * normB;
            const remainder = numerator % denominator;

            // 完全に割り切れる、または誤差が最小のペアを記録
            if (remainder < minError) {
                minError = remainder;
                bestMatch = {
                    vec_ref,
                    vec_cand,
                    normA,
                    normB,
                    dotProduct,
                    remainder,
                    similarity: Math.round(numerator / denominator)
                };

                // 完全一致が見つかったら即座に返す
                if (remainder === 0) {
                    return bestMatch;
                }
            }
        }
    }

    return bestMatch;
}

/**
 * ノルム計算
 */
function calculateNorm(vector) {
    const sumOfSquares = vector.reduce((sum, val) => sum + val * val, 0);
    return Math.round(Math.sqrt(sumOfSquares));
}

/**
 * 内積計算
 */
function calculateDotProduct(vecA, vecB) {
    return vecA.reduce((sum, val, idx) => sum + val * vecB[idx], 0);
}

/**
 * コサイン類似度を計算
 */
function calculateCosineSimilarity(vecA, vecB, scale = SCALE) {
    const dotProduct = calculateDotProduct(vecA, vecB);
    const normA = calculateNorm(vecA);
    const normB = calculateNorm(vecB);

    if (normA === 0 || normB === 0) {
        return { similarity: 0, normA: 0, normB: 0, dotProduct: 0 };
    }

    const similarity = Math.round((dotProduct * scale) / (normA * normB));

    return { similarity, normA, normB, dotProduct };
}

/**
 * ZKP証明を生成
 */
async function generateProof(input) {
    console.log('\n⚙️  Calculating witness and generating proof...');

    const wasmFile = path.join(BUILD_DIR, 'csi_subcarrier_selector_js/csi_subcarrier_selector.wasm');
    const zkeyFile = path.join(KEYS_DIR, 'csi_subcarrier_selector.zkey');

    const { proof, publicSignals } = await snarkjs.groth16.fullProve(
        input,
        wasmFile,
        zkeyFile
    );

    console.log('✅ Proof generation complete!');

    const bestIndex = parseInt(publicSignals[0]);
    const bestSimilarity = parseInt(publicSignals[1]);
    const hasValidCandidate = parseInt(publicSignals[2]);

    console.log('\n📤 Public outputs:');
    console.log(`  Best Index: ${bestIndex}`);
    console.log(`  Best Similarity: ${bestSimilarity} (${(bestSimilarity/SCALE).toFixed(4)})`);
    console.log(`  Has Valid Candidate: ${hasValidCandidate} (${hasValidCandidate ? 'YES' : 'NO'})`);

    return { proof, publicSignals };
}

/**
 * 証明を保存
 */
async function saveProof(proof, publicSignals) {
    const proofFile = path.join(PROOFS_DIR, 'csi_fft_exact_proof.json');
    const publicFile = path.join(PROOFS_DIR, 'csi_fft_exact_public.json');

    await fs.promises.writeFile(proofFile, JSON.stringify(proof, null, 2));
    await fs.promises.writeFile(publicFile, JSON.stringify(publicSignals, null, 2));

    console.log('\n💾 Files saved:');
    console.log(`  Proof: ${proofFile}`);
    console.log(`  Public signals: ${publicFile}`);
}

/**
 * メイン処理
 */
async function main() {
    try {
        console.log('🔐 Generating ZKP proof from FFT CSI data (EXACT MATCH)...\n');

        // 1. FFT CSVファイルを読み込み
        const fftData = await loadFFTDataFromCSV(FFT_CSV_FILE);

        console.log('\n📊 Finding exact matching vectors from FFT data...');
        console.log('   (Searching for vectors where verification equation holds exactly)\n');

        // 2. 検証式が完全に成立するベクトルペアを探索
        // SC 0は値が小さすぎるため、SC 1を参照として使用
        const refData = fftData[1].powerBins.slice(0, 4);
        const cand1Data = fftData[10]?.powerBins.slice(0, 4) || fftData[2].powerBins.slice(0, 4);
        const cand2Data = fftData[20]?.powerBins.slice(0, 4) || fftData[3].powerBins.slice(0, 4);

        console.log(`   Raw FFT data (first 4 bins):`);
        console.log(`   Reference (SC 1): [${refData.map(v => v.toExponential(2)).join(', ')}]`);
        console.log(`   Candidate 1 (SC 10): [${cand1Data.map(v => v.toExponential(2)).join(', ')}]`);
        console.log(`   Candidate 2 (SC 20): [${cand2Data.map(v => v.toExponential(2)).join(', ')}]`);

        const match1 = findExactMatchingVectors(refData, cand1Data);
        const match2 = findExactMatchingVectors(refData, cand2Data);

        console.log(`\n   ✅ Found vectors with minimal verification error:`);
        console.log(`   Reference: [${match1.vec_ref.join(', ')}] (norm=${match1.normA})`);
        console.log(`   Candidate 1: [${match1.vec_cand.join(', ')}] (norm=${match1.normB})`);
        console.log(`     Similarity: ${match1.similarity} (${(match1.similarity/SCALE).toFixed(4)})`);
        console.log(`     Verification remainder: ${match1.remainder} ${match1.remainder === 0 ? '✅ EXACT' : '⚠️'}`);

        console.log(`   Candidate 2: [${match2.vec_cand.join(', ')}] (norm=${match2.normB})`);
        console.log(`     Similarity: ${match2.similarity} (${(match2.similarity/SCALE).toFixed(4)})`);
        console.log(`     Verification remainder: ${match2.remainder} ${match2.remainder === 0 ? '✅ EXACT' : '⚠️'}`);

        // 3. 回路入力を準備
        const input = {
            reference: match1.vec_ref,
            candidates: [match1.vec_cand, match2.vec_cand],
            referenceNorm: match1.normA,
            candidateNorms: [match1.normB, match2.normB],
            similarities: [match1.similarity, match2.similarity]
        };

        console.log('\n📊 Circuit input prepared');

        // 4. ZKP証明を生成
        const { proof, publicSignals } = await generateProof(input);

        // 5. 証明を保存
        await saveProof(proof, publicSignals);

        console.log('\n✅ All operations successful!');
        console.log('\nNext step: Verify the proof');
        console.log('  node scripts/verify_csi_fft.js');

    } catch (error) {
        console.error('\n❌ Error:', error.message);
        console.error(error.stack);
        process.exit(1);
    }
}

// スクリプト実行
main();
