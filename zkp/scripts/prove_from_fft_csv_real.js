#!/usr/bin/env node

/**
 * FFT周波数成分CSVからZKP証明を生成（実データ丸め版）
 *
 * 実際のFFTデータを可能な限り使用し、丸め処理で整数化を試みます。
 * 注意：検証式の丸め誤差により失敗する可能性が高いです。
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

        // 最初の4周波数ビンを抽出（低周波成分）
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
 * パワースペクトルから4次元ベクトルを生成（実データ丸め）
 *
 * アプローチ:
 * - 実際のFFTデータを使用
 * - 正規化してスケーリング
 * - 丸め処理で整数化
 * - 検証式の誤差を最小化する試み
 */
function convertFFTToVectors(fftData) {
    console.log('\n📊 Converting FFT power spectrum to 4D vectors (REAL DATA ROUNDING)...');

    // SC 1を参照（SC 0は値が小さすぎる）
    const refData = fftData[1].powerBins.slice(0, 4);

    // 候補1: SC 10
    const cand1Data = fftData[10]?.powerBins.slice(0, 4) || fftData[2].powerBins.slice(0, 4);

    // 候補2: SC 20
    const cand2Data = fftData[20]?.powerBins.slice(0, 4) || fftData[3].powerBins.slice(0, 4);

    console.log(`\n   Raw FFT data (first 4 bins):`);
    console.log(`   Reference (SC 1): [${refData.map(v => v.toExponential(2)).join(', ')}]`);
    console.log(`   Candidate 1 (SC 10): [${cand1Data.map(v => v.toExponential(2)).join(', ')}]`);
    console.log(`   Candidate 2 (SC 20): [${cand2Data.map(v => v.toExponential(2)).join(', ')}]`);

    // 実データを整数ベクトルに変換（丸め処理）
    const reference = convertToIntegerVector(refData, 'Reference');
    const candidate1 = convertToIntegerVector(cand1Data, 'Candidate 1');
    const candidate2 = convertToIntegerVector(cand2Data, 'Candidate 2');

    console.log(`\n   Converted to integer vectors:`);
    console.log(`   Reference: [${reference.join(', ')}] (norm=${calculateNorm(reference)})`);
    console.log(`   Candidate 1: [${candidate1.join(', ')}] (norm=${calculateNorm(candidate1)})`);
    console.log(`   Candidate 2: [${candidate2.join(', ')}] (norm=${calculateNorm(candidate2)})`);
    console.log(`   ⚠️  Warning: Using real data with rounding - verification may fail`);

    return {
        reference,
        candidate1,
        candidate2
    };
}

/**
 * 実データを整数ベクトルに変換
 *
 * 戦略:
 * 1. 正規化（最大値で割る）
 * 2. 複数のスケールを試行
 * 3. ノルムが整数に最も近いものを選択
 */
function convertToIntegerVector(data, label) {
    const maxVal = Math.max(...data.map(Math.abs));
    if (maxVal === 0) return [0, 0, 0, 0];

    const normalized = data.map(v => v / maxVal);

    let bestVector = null;
    let bestScore = -Infinity;

    // スケール3-15で探索
    for (let scale = 3; scale <= 15; scale++) {
        const scaled = normalized.map(v => Math.round(v * scale));

        // ノルムの整数近似度を評価
        const normSquared = scaled.reduce((sum, v) => sum + v * v, 0);
        const norm = Math.sqrt(normSquared);
        const normInt = Math.round(norm);
        const normError = Math.abs(norm - normInt);

        // スコア：ノルムが整数に近く、値が適度に大きい
        const score = (normInt / (1 + normError * 100));

        if (score > bestScore && normInt > 0) {
            bestScore = score;
            bestVector = scaled;
        }
    }

    return bestVector || [0, 0, 0, 0];
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
        return { similarity: 0, normA: 0, normB: 0, dotProduct: 0 };
    }

    const similarity = Math.round((dotProduct * scale) / (normA * normB));

    return { similarity, normA, normB, dotProduct };
}

/**
 * ZKP回路入力データを準備
 */
function prepareCircuitInput(vectors) {
    const { reference, candidate1, candidate2 } = vectors;

    const refNorm = calculateNorm(reference);
    const cand1Metrics = calculateCosineSimilarity(reference, candidate1);
    const cand2Metrics = calculateCosineSimilarity(reference, candidate2);

    const input = {
        reference: reference,
        candidates: [candidate1, candidate2],
        referenceNorm: refNorm,
        candidateNorms: [cand1Metrics.normB, cand2Metrics.normB],
        similarities: [cand1Metrics.similarity, cand2Metrics.similarity]
    };

    console.log('\n📊 Circuit input prepared:');
    console.log(`   Reference Norm: ${refNorm}`);
    console.log(`   Candidate 1: Norm=${cand1Metrics.normB}, Similarity=${cand1Metrics.similarity} (${(cand1Metrics.similarity/10000).toFixed(4)})`);
    console.log(`   Candidate 2: Norm=${cand2Metrics.normB}, Similarity=${cand2Metrics.similarity} (${(cand2Metrics.similarity/10000).toFixed(4)})`);

    // 検証式の誤差をチェック
    console.log('\n🔍 Verification equation check:');
    checkVerificationEquation(reference, candidate1, cand1Metrics);
    checkVerificationEquation(reference, candidate2, cand2Metrics);

    return input;
}

/**
 * 検証式の誤差をチェック
 */
function checkVerificationEquation(ref, cand, metrics) {
    const { similarity, normA, normB, dotProduct } = metrics;
    const lhs = similarity * normA * normB;
    const rhs = dotProduct * 10000;
    const error = Math.abs(lhs - rhs);

    console.log(`   ${lhs} = ${rhs} ? Error: ${error} ${error === 0 ? '✅' : '❌'}`);
}

/**
 * ZKP証明を生成
 */
async function generateProof(input) {
    console.log('\n⚙️  Calculating witness and generating proof...');
    console.log('   (This will likely fail due to rounding errors)');

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
    console.log(`  Best Similarity: ${bestSimilarity} (${(bestSimilarity/10000).toFixed(4)})`);
    console.log(`  Has Valid Candidate: ${hasValidCandidate} (${hasValidCandidate ? 'YES' : 'NO'})`);

    return { proof, publicSignals };
}

/**
 * 証明とpublic signalsをファイルに保存
 */
async function saveProof(proof, publicSignals) {
    const proofFile = path.join(PROOFS_DIR, 'csi_fft_real_proof.json');
    const publicFile = path.join(PROOFS_DIR, 'csi_fft_real_public.json');

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
        console.log('🔐 Generating ZKP proof from FFT CSI data (REAL DATA ROUNDING)...\n');

        // 1. FFT CSVファイルを読み込み
        const fftData = await loadFFTDataFromCSV(FFT_CSV_FILE);

        // 2. 実際のFFTデータからベクトルを生成（丸め処理）
        const vectors = convertFFTToVectors(fftData);

        // 3. 回路入力を準備
        const input = prepareCircuitInput(vectors);

        // 4. ZKP証明を生成
        const { proof, publicSignals } = await generateProof(input);

        // 5. 証明を保存
        await saveProof(proof, publicSignals);

        console.log('\n✅ All operations successful!');
        console.log('   🎉 Real data rounding approach SUCCEEDED!');
        console.log('\nNext step: Verify the proof');
        console.log('  node scripts/verify_csi_fft_real.js');

    } catch (error) {
        console.error('\n❌ Error:', error.message);
        if (error.message.includes('Assert Failed')) {
            console.error('\n💡 As expected: Verification equation failed due to rounding errors');
            console.error('   This demonstrates why Pythagorean triple patterns are necessary');
        }
        process.exit(1);
    }
}

// スクリプト実行
main();
