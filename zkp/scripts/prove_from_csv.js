#!/usr/bin/env node

/**
 * CSVファイルからCSIデータを読み込んでZKP証明を生成
 *
 * PythonスクリプトでPCAPから抽出したCSIデータを使用して
 * サブキャリア選択のZKP証明を生成します。
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

const CSV_FILE = path.join(DATA_DIR, 'csi_amplitudes.csv');

/**
 * CSVファイルからCSI振幅データを読み込み
 */
async function loadCSIDataFromCSV(csvPath) {
    console.log('📂 Loading CSI data from CSV...');
    console.log(`   File: ${csvPath}`);

    if (!fs.existsSync(csvPath)) {
        throw new Error(`CSV file not found: ${csvPath}`);
    }

    const jsonArray = await csv().fromFile(csvPath);

    console.log(`✅ Loaded ${jsonArray.length} CSI packets`);

    // サブキャリアデータを抽出
    const amplitudesArray = jsonArray.map(row => {
        const subcarriers = [];
        for (let i = 0; i < 64; i++) {
            const key = `subcarrier_${i}`;
            if (row[key]) {
                subcarriers.push(parseFloat(row[key]));
            }
        }
        return subcarriers;
    });

    // 統計情報を表示
    const firstPacket = amplitudesArray[0];
    const meanAmp = firstPacket.reduce((sum, val) => sum + val, 0) / firstPacket.length;
    console.log(`   Subcarriers per packet: ${firstPacket.length}`);
    console.log(`   Mean amplitude (packet 0): ${meanAmp.toFixed(4)}`);

    return amplitudesArray;
}

/**
 * CSI振幅データから4次元ベクトルを生成
 *
 * 実際のCSIデータの特性を保持しつつ、
 * ノルムが整数になるように調整します。
 */
function generateVectorsFromRealCSI(amplitudesArray) {
    console.log('\n📊 Generating vectors from real CSI data...');

    // 最初のパケットの最初の4サブキャリアを使用
    const firstPacketAmps = amplitudesArray[0].slice(0, 4);

    // 正規化してスケーリング（ピタゴラス数に近づける）
    const maxAmp = Math.max(...firstPacketAmps);
    const normalized = firstPacketAmps.map(amp => amp / maxAmp);

    // ピタゴラス数パターン [3, 4, 0, 0] にマッピング
    const reference = [
        Math.round(normalized[0] * 3),
        Math.round(normalized[1] * 4),
        0,
        0
    ];

    // 候補1: わずかに異なるパターン（高類似度）
    const candidate1 = [
        Math.round(normalized[1] * 4),
        Math.round(normalized[0] * 3),
        0,
        0
    ];

    // 候補2: より異なるパターン（低類似度）
    const candidate2 = [
        Math.round(normalized[0] * 3),
        0,
        Math.round(normalized[1] * 4),
        0
    ];

    console.log(`   Reference: [${reference.join(', ')}]`);
    console.log(`   Candidate 1: [${candidate1.join(', ')}]`);
    console.log(`   Candidate 2: [${candidate2.join(', ')}]`);

    return { reference, candidate1, candidate2 };
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

    return input;
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
    console.log(`  Best Similarity: ${bestSimilarity} (${(bestSimilarity/10000).toFixed(4)})`);
    console.log(`  Has Valid Candidate: ${hasValidCandidate} (${hasValidCandidate ? 'YES' : 'NO'})`);

    return { proof, publicSignals };
}

/**
 * 証明とpublic signalsをファイルに保存
 */
async function saveProof(proof, publicSignals) {
    const proofFile = path.join(PROOFS_DIR, 'csi_csv_proof.json');
    const publicFile = path.join(PROOFS_DIR, 'csi_csv_public.json');

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
        console.log('🔐 Generating ZKP proof from CSV CSI data...\n');

        // 1. CSVファイルからCSIデータを読み込み
        const amplitudesArray = await loadCSIDataFromCSV(CSV_FILE);

        // 2. 実際のCSIデータからベクトルを生成
        const vectors = generateVectorsFromRealCSI(amplitudesArray);

        // 3. 回路入力を準備
        const input = prepareCircuitInput(vectors);

        // 4. ZKP証明を生成
        const { proof, publicSignals } = await generateProof(input);

        // 5. 証明を保存
        await saveProof(proof, publicSignals);

        console.log('\n✅ All operations successful!');
        console.log('\nNext step: Verify the proof');
        console.log('  node scripts/verify_csi_csv.js');

    } catch (error) {
        console.error('\n❌ Error:', error.message);
        if (error.message.includes('CSV file not found')) {
            console.error('\nPlease run the Python extraction script first:');
            console.error('  python3 scripts/extract_csi_to_csv.py');
        }
        process.exit(1);
    }
}

// スクリプト実行
main();
