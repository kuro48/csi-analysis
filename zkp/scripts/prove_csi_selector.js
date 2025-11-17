#!/usr/bin/env node

/**
 * CSI Subcarrier Selector 証明生成スクリプト
 * 動作確認済みの csi_subcarrier_selector 回路を使用
 */

const snarkjs = require('snarkjs');
const path = require('path');
const fs = require('fs');

const CIRCUIT_NAME = 'csi_subcarrier_selector';
const BUILD_DIR = path.join(__dirname, '../build');
const KEYS_DIR = path.join(__dirname, '../keys');
const PROOFS_DIR = path.join(__dirname, '../proofs');

// proofsディレクトリの作成
if (!fs.existsSync(PROOFS_DIR)) {
    fs.mkdirSync(PROOFS_DIR, { recursive: true });
}

/**
 * ベクトルのノルム計算
 */
function calculateNorm(vector) {
    const sumSquares = vector.reduce((sum, val) => sum + val * val, 0);
    return Math.floor(Math.sqrt(sumSquares));
}

/**
 * 類似度計算
 */
function calculateSimilarity(vectorA, vectorB, normA, normB, scale) {
    const dotProduct = vectorA.reduce((sum, val, i) => sum + val * vectorB[i], 0);
    const numerator = dotProduct * scale;
    const denominator = normA * normB;
    return Math.floor(numerator / denominator);
}

/**
 * 証明生成
 */
async function generateProof() {
    try {
        console.log('🔐 Generating proof for CSI subcarrier selector...\n');

        const SCALE = 10000; // 固定小数点スケール

        // サンプル入力データ（ノルムが整数になるベクトル）
        // 類似度テスト: 低い類似度を選択
        const reference = [3, 4, 0, 0];  // ノルム = 5
        const candidates = [
            [4, 3, 0, 0],    // 候補1: 成分入れ替え（類似度高い: 0.96）
            [3, 0, 4, 0]     // 候補2: 直交に近い（類似度低い: 0.36）
        ];

        // ノルム計算
        const referenceNorm = calculateNorm(reference);
        const candidateNorms = candidates.map(c => calculateNorm(c));

        // 類似度計算
        const similarities = candidates.map((c, i) =>
            calculateSimilarity(reference, c, referenceNorm, candidateNorms[i], SCALE)
        );

        console.log('📊 Input data:');
        console.log(`  Reference: [${reference.join(', ')}]`);
        console.log(`  Reference Norm: ${referenceNorm}`);
        console.log(`\n  Candidate 1: [${candidates[0].join(', ')}]`);
        console.log(`  Candidate 1 Norm: ${candidateNorms[0]}`);
        console.log(`  Candidate 1 Similarity: ${similarities[0]} (${(similarities[0]/SCALE).toFixed(4)})`);
        console.log(`\n  Candidate 2: [${candidates[1].join(', ')}]`);
        console.log(`  Candidate 2 Norm: ${candidateNorms[1]}`);
        console.log(`  Candidate 2 Similarity: ${similarities[1]} (${(similarities[1]/SCALE).toFixed(4)})`);

        const input = {
            reference: reference,
            candidates: candidates,
            candidateNorms: candidateNorms,
            similarities: similarities,
            referenceNorm: referenceNorm
        };

        // 必要なファイルパス
        const wasmFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}_js`, `${CIRCUIT_NAME}.wasm`);
        const zkeyFile = path.join(KEYS_DIR, `${CIRCUIT_NAME}.zkey`);

        // ファイル存在確認
        if (!fs.existsSync(wasmFile)) {
            throw new Error(`WASM file not found: ${wasmFile}\nRun compile_csi_selector.js first.`);
        }
        if (!fs.existsSync(zkeyFile)) {
            throw new Error(`zKey file not found: ${zkeyFile}\nRun setup_csi_selector.js first.`);
        }

        console.log('\n⚙️  Calculating witness and generating proof...');

        // Witness計算と証明生成
        const { proof, publicSignals } = await snarkjs.groth16.fullProve(
            input,
            wasmFile,
            zkeyFile
        );

        console.log('✅ Proof generation complete!');
        console.log('\n📤 Public outputs:');
        console.log(`  Best Index: ${publicSignals[0]}`);
        console.log(`  Best Similarity: ${publicSignals[1]} (${(publicSignals[1]/SCALE).toFixed(4)})`);
        console.log(`  Has Valid Candidate: ${publicSignals[2]} (${publicSignals[2] === '1' ? 'YES' : 'NO'})`);

        // 証明とpublic signalsの保存
        const proofFile = path.join(PROOFS_DIR, `${CIRCUIT_NAME}_proof.json`);
        const publicFile = path.join(PROOFS_DIR, `${CIRCUIT_NAME}_public.json`);

        fs.writeFileSync(proofFile, JSON.stringify(proof, null, 2));
        fs.writeFileSync(publicFile, JSON.stringify(publicSignals, null, 2));

        console.log('\n💾 Files saved:');
        console.log(`  Proof: ${proofFile}`);
        console.log(`  Public signals: ${publicFile}`);

        console.log('\n✅ All operations successful!');

    } catch (error) {
        console.error('\n❌ Proof generation failed:', error.message);
        if (error.stack) {
            console.error(error.stack);
        }
        process.exit(1);
    }
}

generateProof();
