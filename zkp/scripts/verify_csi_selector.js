#!/usr/bin/env node

/**
 * CSI Subcarrier Selector 証明検証スクリプト
 */

const snarkjs = require('snarkjs');
const path = require('path');
const fs = require('fs');

const CIRCUIT_NAME = 'csi_subcarrier_selector';
const KEYS_DIR = path.join(__dirname, '../keys');
const PROOFS_DIR = path.join(__dirname, '../proofs');

/**
 * 証明検証
 */
async function verifyProof() {
    try {
        console.log('🔍 Verifying proof for CSI subcarrier selector...\n');

        // 必要なファイルパス
        const vKeyFile = path.join(KEYS_DIR, `${CIRCUIT_NAME}_verification_key.json`);
        const proofFile = path.join(PROOFS_DIR, `${CIRCUIT_NAME}_proof.json`);
        const publicFile = path.join(PROOFS_DIR, `${CIRCUIT_NAME}_public.json`);

        // ファイル存在確認
        if (!fs.existsSync(vKeyFile)) {
            throw new Error(`Verification key not found: ${vKeyFile}\nRun setup_csi_selector.js first.`);
        }
        if (!fs.existsSync(proofFile)) {
            throw new Error(`Proof file not found: ${proofFile}\nRun prove_csi_selector.js first.`);
        }
        if (!fs.existsSync(publicFile)) {
            throw new Error(`Public signals file not found: ${publicFile}\nRun prove_csi_selector.js first.`);
        }

        // ファイルの読み込み
        const vKey = JSON.parse(fs.readFileSync(vKeyFile, 'utf8'));
        const proof = JSON.parse(fs.readFileSync(proofFile, 'utf8'));
        const publicSignals = JSON.parse(fs.readFileSync(publicFile, 'utf8'));

        const SCALE = 10000;

        console.log('📤 Public signals:');
        console.log(`  Best Index: ${publicSignals[0]}`);
        console.log(`  Best Similarity: ${publicSignals[1]} (${(publicSignals[1]/SCALE).toFixed(4)})`);
        console.log(`  Has Valid Candidate: ${publicSignals[2]} (${publicSignals[2] === '1' ? 'YES' : 'NO'})`);

        console.log('\n⚙️  Verifying proof...');

        // 証明検証
        const isValid = await snarkjs.groth16.verify(vKey, publicSignals, proof);

        console.log('\n' + '='.repeat(60));
        if (isValid) {
            console.log('✅ PROOF VERIFIED SUCCESSFULLY!');
            console.log('   The proof is cryptographically valid.');
            console.log('   CSI subcarrier selection computation is correct.');
        } else {
            console.log('❌ PROOF VERIFICATION FAILED!');
            console.log('   The proof is invalid or tampered.');
        }
        console.log('='.repeat(60));

        return isValid;

    } catch (error) {
        console.error('\n❌ Verification failed:', error.message);
        process.exit(1);
    }
}

verifyProof();
