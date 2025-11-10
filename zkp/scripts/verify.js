#!/usr/bin/env node

/**
 * ZKP証明の検証スクリプト
 */

const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');

const CIRCUIT_NAME = 'breathing_verifier';
const BUILD_DIR = path.join(__dirname, '../build');
const KEYS_DIR = path.join(__dirname, '../keys');

/**
 * 証明の検証
 */
function verifyProof() {
    return new Promise((resolve, reject) => {
        const vKeyFile = path.join(KEYS_DIR, 'verification_key.json');
        const proofFile = path.join(BUILD_DIR, 'proof.json');
        const publicFile = path.join(BUILD_DIR, 'public.json');

        if (!fs.existsSync(vKeyFile)) {
            reject(new Error('Verification key not found. Please run setup first.'));
            return;
        }

        if (!fs.existsSync(proofFile) || !fs.existsSync(publicFile)) {
            reject(new Error('Proof files not found. Please run prove first.'));
            return;
        }

        console.log('🔍 Verifying proof...');

        const verifyCmd = `snarkjs groth16 verify ${vKeyFile} ${publicFile} ${proofFile}`;

        const startTime = Date.now();

        exec(verifyCmd, (error, stdout, stderr) => {
            const endTime = Date.now();
            const duration = ((endTime - startTime) / 1000).toFixed(3);

            if (error) {
                console.error('❌ Proof verification failed:');
                console.error(stderr);
                reject(error);
                return;
            }

            // 出力から検証結果を判定
            const isValid = stdout.includes('OK');

            if (isValid) {
                console.log(`✅ Proof is VALID! (verified in ${duration}s)`);
            } else {
                console.log(`❌ Proof is INVALID!`);
            }

            // 公開入力の表示
            const publicSignals = JSON.parse(fs.readFileSync(publicFile, 'utf8'));
            console.log('\n📋 Public Signals:');
            console.log('   isValid (output):', publicSignals[0]);
            console.log('   Breathing Rate:', publicSignals[1], 'bpm');
            console.log('   Confidence Score:', publicSignals[2], '%');

            resolve(isValid);
        });
    });
}

/**
 * メイン処理
 */
async function main() {
    try {
        console.log('🚀 Starting proof verification...\n');

        const isValid = await verifyProof();

        if (isValid) {
            console.log('\n✅ Verification complete! Proof is valid.');
            process.exit(0);
        } else {
            console.log('\n❌ Verification complete! Proof is invalid.');
            process.exit(1);
        }

    } catch (error) {
        console.error('\n❌ Verification failed:', error.message);
        process.exit(1);
    }
}

main();
