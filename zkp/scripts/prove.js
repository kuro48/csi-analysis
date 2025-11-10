#!/usr/bin/env node

/**
 * ZKP証明の生成スクリプト
 * テストデータを使用して証明を生成
 */

const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');

const CIRCUIT_NAME = 'breathing_verifier';
const BUILD_DIR = path.join(__dirname, '../build');
const KEYS_DIR = path.join(__dirname, '../keys');

/**
 * サンプル入力データの生成（超シンプル版）
 */
function generateSampleInput() {
    // シンプルな入力データ
    const breathingRate = 15; // 15 bpm（正常範囲: 10-30）
    const confidenceScore = 85; // 85%（閾値: 70以上）

    return {
        breathingRate,
        confidenceScore
    };
}

/**
 * witness の計算
 */
function calculateWitness(inputData) {
    return new Promise((resolve, reject) => {
        const wasmFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}_js`, `${CIRCUIT_NAME}.wasm`);
        const inputFile = path.join(BUILD_DIR, 'input.json');
        const witnessFile = path.join(BUILD_DIR, 'witness.wtns');

        // 入力データをファイルに保存
        fs.writeFileSync(inputFile, JSON.stringify(inputData, null, 2));

        console.log('🧮 Calculating witness...');

        const witnessCmd = `snarkjs wtns calculate ${wasmFile} ${inputFile} ${witnessFile}`;

        exec(witnessCmd, (error, stdout, stderr) => {
            if (error) {
                console.error('❌ Witness calculation failed:');
                console.error(stderr);
                reject(error);
                return;
            }

            console.log('✅ Witness calculated!');
            resolve(witnessFile);
        });
    });
}

/**
 * 証明の生成
 */
function generateProof(witnessFile) {
    return new Promise((resolve, reject) => {
        const zKeyFile = path.join(KEYS_DIR, `${CIRCUIT_NAME}.zkey`);
        const proofFile = path.join(BUILD_DIR, 'proof.json');
        const publicFile = path.join(BUILD_DIR, 'public.json');

        if (!fs.existsSync(zKeyFile)) {
            reject(new Error('zKey file not found. Please run setup first.'));
            return;
        }

        console.log('🔐 Generating proof...');

        const proveCmd = `snarkjs groth16 prove ${zKeyFile} ${witnessFile} ${proofFile} ${publicFile}`;

        const startTime = Date.now();

        exec(proveCmd, (error, stdout, stderr) => {
            if (error) {
                console.error('❌ Proof generation failed:');
                console.error(stderr);
                reject(error);
                return;
            }

            const endTime = Date.now();
            const duration = ((endTime - startTime) / 1000).toFixed(2);

            console.log(`✅ Proof generated in ${duration}s!`);
            console.log(`   Proof: ${proofFile}`);
            console.log(`   Public signals: ${publicFile}`);

            // 証明データの読み込みと表示
            const proof = JSON.parse(fs.readFileSync(proofFile, 'utf8'));
            const publicSignals = JSON.parse(fs.readFileSync(publicFile, 'utf8'));

            console.log('\n📋 Proof Summary:');
            console.log(`   Protocol: Groth16`);
            console.log(`   Curve: bn128`);
            console.log(`   Public inputs: ${publicSignals.length}`);

            resolve({ proof, publicSignals });
        });
    });
}

/**
 * メイン処理
 */
async function main() {
    try {
        console.log('🚀 Starting proof generation...\n');

        // 1. サンプル入力データの生成
        console.log('📝 Generating sample input data...');
        const inputData = generateSampleInput();
        console.log('   Breathing rate:', inputData.breathingRate, 'bpm');
        console.log('   Confidence:', inputData.confidenceScore, '%');

        // 2. Witness の計算
        const witnessFile = await calculateWitness(inputData);

        // 3. 証明の生成
        const { proof, publicSignals } = await generateProof(witnessFile);

        console.log('\n✅ Proof generation complete!');
        console.log('   Use "npm run verify" to verify this proof.');

    } catch (error) {
        console.error('\n❌ Proof generation failed:', error.message);
        process.exit(1);
    }
}

main();
