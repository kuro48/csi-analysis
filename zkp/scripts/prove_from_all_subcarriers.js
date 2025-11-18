#!/usr/bin/env node

/**
 * 64サブキャリアの実データからZKP証明を生成
 *
 * 全64サブキャリアのPythagorean triple近似データを使用し、
 * 指定されたサブキャリアペアのコサイン類似度をZKPで証明します。
 */

const fs = require('fs');
const path = require('path');
const snarkjs = require('snarkjs');

// ファイルパス設定
const DATA_DIR = path.join(__dirname, '../data');
const BUILD_DIR = path.join(__dirname, '../build');
const KEYS_DIR = path.join(__dirname, '../keys');
const PROOFS_DIR = path.join(__dirname, '../proofs');
const SIMILARITY_DIR = path.join(DATA_DIR, 'similarity_results');

const CONVERTED_VECTORS_FILE = path.join(SIMILARITY_DIR, 'converted_vectors.json');

/**
 * 変換済みベクトルを読み込み
 */
function loadConvertedVectors() {
    console.log('📂 Loading converted vectors from similarity results...');
    console.log(`   File: ${CONVERTED_VECTORS_FILE}`);

    if (!fs.existsSync(CONVERTED_VECTORS_FILE)) {
        throw new Error(`Converted vectors file not found. Please run calculate_all_subcarrier_similarity.js first.`);
    }

    const data = JSON.parse(fs.readFileSync(CONVERTED_VECTORS_FILE, 'utf8'));
    console.log(`✅ Loaded ${data.length} converted subcarrier vectors`);

    return data;
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
 *
 * @param {Object} reference - 参照サブキャリア
 * @param {Array<Object>} candidates - 候補サブキャリア配列（最大2つ）
 */
function prepareCircuitInput(reference, candidates) {
    const refNorm = reference.norm;
    const candidateMetrics = candidates.map(cand =>
        calculateCosineSimilarity(reference.vector, cand.vector)
    );

    const input = {
        reference: reference.vector,
        candidates: candidates.map(c => c.vector),
        referenceNorm: refNorm,
        candidateNorms: candidateMetrics.map(m => m.normB),
        similarities: candidateMetrics.map(m => m.similarity)
    };

    console.log('\n📊 Circuit input prepared:');
    console.log(`   Reference: SC ${reference.subcarrierId}, Vector: [${reference.vector.join(', ')}], Norm: ${refNorm}`);

    candidates.forEach((cand, idx) => {
        const metrics = candidateMetrics[idx];
        console.log(`   Candidate ${idx + 1}: SC ${cand.subcarrierId}, Vector: [${cand.vector.join(', ')}], Norm: ${metrics.normB}, Similarity: ${metrics.similarity} (${(metrics.similarity/10000).toFixed(4)})`);
    });

    // 検証式の誤差をチェック
    console.log('\n🔍 Verification equation check:');
    candidates.forEach((cand, idx) => {
        const metrics = candidateMetrics[idx];
        const lhs = metrics.similarity * refNorm * metrics.normB;
        const rhs = metrics.dotProduct * 10000;
        const error = Math.abs(lhs - rhs);
        console.log(`   Candidate ${idx + 1}: ${lhs} = ${rhs} ? Error: ${error} ${error === 0 ? '✅' : '❌'}`);
    });

    return input;
}

/**
 * ZKP証明を生成
 */
async function generateProof(input, reference, candidates) {
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
    console.log(`  Best Candidate: SC ${candidates[bestIndex].subcarrierId}`);
    console.log(`  Best Similarity: ${bestSimilarity} (${(bestSimilarity/10000).toFixed(4)})`);
    console.log(`  Has Valid Candidate: ${hasValidCandidate} (${hasValidCandidate ? 'YES' : 'NO'})`);

    return { proof, publicSignals };
}

/**
 * 証明とpublic signalsをファイルに保存
 */
async function saveProof(proof, publicSignals, reference, candidates) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0];
    const candidateIds = candidates.map(c => c.subcarrierId).join('_');
    const proofFile = path.join(PROOFS_DIR, `proof_sc${reference.subcarrierId}_vs_${candidateIds}.json`);
    const publicFile = path.join(PROOFS_DIR, `public_sc${reference.subcarrierId}_vs_${candidateIds}.json`);

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
        console.log('🔐 Generating ZKP proof from 64 subcarrier real data...\n');

        // コマンドライン引数を解析
        const args = process.argv.slice(2);
        let referenceId = 1;  // デフォルト参照: SC 1
        let candidateIds = [10, 20];  // デフォルト候補: SC 10, SC 20

        if (args.length > 0) {
            referenceId = parseInt(args[0]);
        }
        if (args.length > 1) {
            candidateIds = args.slice(1).map(id => parseInt(id));
        }

        // 最大2候補まで
        if (candidateIds.length > 2) {
            console.log(`⚠️  Warning: Only first 2 candidates will be used (circuit limitation)`);
            candidateIds = candidateIds.slice(0, 2);
        }

        console.log(`📋 Selected subcarriers:`);
        console.log(`   Reference: SC ${referenceId}`);
        console.log(`   Candidates: SC ${candidateIds.join(', SC ')}`);
        console.log();

        // 1. 変換済みベクトルを読み込み
        const allVectors = loadConvertedVectors();

        // 2. 指定されたサブキャリアを取得
        const reference = allVectors.find(v => v.subcarrierId === referenceId);
        if (!reference) {
            throw new Error(`Reference subcarrier ${referenceId} not found`);
        }

        const candidates = candidateIds.map(id => {
            const cand = allVectors.find(v => v.subcarrierId === id);
            if (!cand) {
                throw new Error(`Candidate subcarrier ${id} not found`);
            }
            return cand;
        });

        // 3. 回路入力を準備
        const input = prepareCircuitInput(reference, candidates);

        // 4. ZKP証明を生成
        const { proof, publicSignals } = await generateProof(input, reference, candidates);

        // 5. 証明を保存
        await saveProof(proof, publicSignals, reference, candidates);

        console.log('\n✅ All operations successful!');
        console.log('   🎉 Using REAL 64 subcarrier data with Pythagorean triple approximation!');
        console.log('\nNext step: Verify the proof');
        console.log('  node scripts/verify_csi_fft.js');
        console.log('\nUsage:');
        console.log('  node scripts/prove_from_all_subcarriers.js <reference_id> <candidate1_id> [candidate2_id]');
        console.log('  Example: node scripts/prove_from_all_subcarriers.js 1 10 20');

    } catch (error) {
        console.error('\n❌ Error:', error.message);
        if (error.message.includes('Assert Failed')) {
            console.error('\n💡 Hint: Verification equation failed. Check if vectors have proper integer norms.');
        }
        process.exit(1);
    }
}

// スクリプト実行
main();
