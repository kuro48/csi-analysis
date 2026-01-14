#!/usr/bin/env node

/**
 * ZKP回路で全サブキャリアのコサイン類似度を計算し、証明を生成
 * 上位5つの低類似度サブキャリアを表示（ZKP回路内での計算結果のみ）
 */

const snarkjs = require('snarkjs');
const fs = require('fs');
const path = require('path');

const KEYS_DIR = path.join(__dirname, '../keys');
const BUILD_DIR = path.join(__dirname, '../build');
const WASM_FILE = path.join(BUILD_DIR, 'csi_full_similarity_js', 'csi_full_similarity.wasm');
const ZKEY_FILE = path.join(KEYS_DIR, 'csi_full_similarity_final.zkey');
const VKEY_FILE = path.join(KEYS_DIR, 'csi_full_similarity_verification_key.json');

const NUM_FREQ_POINTS = 25;
const NUM_SUBCARRIERS = 245;
const SCALE = 10000;

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
            // サブキャリアインデックスに応じてノイズレベルを変更
            const noiseLevel = (sc % 50) * 10; // 0-490の範囲
            const noise = (Math.random() - 0.5) * noiseLevel;
            candRow.push(Math.round(baseValue + noise));
        }
        referenceMatrix.push(refRow);
        candidateMatrix.push(candRow);
    }

    return { referenceMatrix, candidateMatrix };
}


/**
 * 上位N個の低類似度サブキャリアを取得
 */
function getTopNLowestSimilarities(similarities, n = 5) {
    const indexed = similarities.map((sim, idx) => ({ index: idx, similarity: sim }));
    indexed.sort((a, b) => a.similarity - b.similarity);
    return indexed.slice(0, n);
}

async function main() {
    try {
        console.log('🚀 Generating ZKP proof for all subcarrier cosine similarities...\n');

        // 必要なファイルの存在確認
        if (!fs.existsSync(WASM_FILE)) {
            console.error(`❌ WASM file not found: ${WASM_FILE}`);
            console.log('Please run: npm run compile:full_similarity');
            process.exit(1);
        }
        if (!fs.existsSync(ZKEY_FILE)) {
            console.error(`❌ ZKey file not found: ${ZKEY_FILE}`);
            console.log('Please run: npm run setup:full_similarity');
            process.exit(1);
        }

        // サンプルデータ生成
        console.log('📊 Generating sample CSI data...');
        const { referenceMatrix, candidateMatrix } = generateSampleCSIData();
        console.log(`  Reference Matrix: ${NUM_FREQ_POINTS} x ${NUM_SUBCARRIERS}`);
        console.log(`  Candidate Matrix: ${NUM_FREQ_POINTS} x ${NUM_SUBCARRIERS}`);

        // 入力データ準備
        const input = {
            referenceMatrix,
            candidateMatrix
        };

        // Witness生成
        console.log('\n⚙️  Generating witness...');
        const { proof, publicSignals } = await snarkjs.groth16.fullProve(
            input,
            WASM_FILE,
            ZKEY_FILE
        );

        console.log('✅ Witness generated successfully');

        // Public signalsから類似度を抽出
        // similarities[0..244], minSimilarity, minIndex
        const zkpSimilarities = publicSignals.slice(0, NUM_SUBCARRIERS).map(s => parseInt(s) / SCALE);
        const zkpMinSimilarity = parseInt(publicSignals[NUM_SUBCARRIERS]) / SCALE;
        const zkpMinIndex = parseInt(publicSignals[NUM_SUBCARRIERS + 1]);

        console.log('\n🔐 ZKP Results:');
        console.log(`  Min Similarity: ${zkpMinSimilarity.toFixed(6)} (Subcarrier ${zkpMinIndex})`);

        // ZKP結果の上位5つ
        const zkpTopN = getTopNLowestSimilarities(zkpSimilarities, 5);
        console.log('\n📉 Top 5 Lowest Similarities (ZKP Circuit):');
        zkpTopN.forEach((item, rank) => {
            console.log(`  ${rank + 1}. Subcarrier ${item.index}: ${item.similarity.toFixed(6)}`);
        });

        // 証明検証
        console.log('\n⚙️  Verifying proof...');
        const vkey = JSON.parse(fs.readFileSync(VKEY_FILE, 'utf8'));
        const isValid = await snarkjs.groth16.verify(vkey, publicSignals, proof);

        if (isValid) {
            console.log('\n============================================================');
            console.log('✅ PROOF VERIFIED SUCCESSFULLY!');
            console.log('   All subcarrier similarities are cryptographically proven.');
            console.log('   Top 5 lowest similarity subcarriers identified.');
            console.log('============================================================');
        } else {
            console.log('\n============================================================');
            console.log('❌ PROOF VERIFICATION FAILED!');
            console.log('============================================================');
            process.exit(1);
        }

        // 結果をファイルに保存（オプション）
        const resultsDir = path.join(__dirname, '../results');
        if (!fs.existsSync(resultsDir)) {
            fs.mkdirSync(resultsDir, { recursive: true });
        }

        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const resultsFile = path.join(resultsDir, `similarities_${timestamp}.json`);

        const results = {
            timestamp: new Date().toISOString(),
            num_subcarriers: NUM_SUBCARRIERS,
            num_freq_points: NUM_FREQ_POINTS,
            zkp_results: {
                top_5: zkpTopN,
                min_similarity: zkpMinSimilarity,
                min_index: zkpMinIndex,
                all_similarities: zkpSimilarities
            },
            proof_valid: isValid,
            input_data: {
                referenceMatrix: referenceMatrix,
                candidateMatrix: candidateMatrix
            }
        };

        fs.writeFileSync(resultsFile, JSON.stringify(results, null, 2));
        console.log(`\n💾 Results saved to: ${resultsFile}`);

    } catch (error) {
        console.error('\n❌ Error:', error.message);
        if (error.stack) {
            console.error(error.stack);
        }
        process.exit(1);
    }
}

main();
