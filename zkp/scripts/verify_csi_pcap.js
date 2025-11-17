#!/usr/bin/env node

/**
 * PCAP CSIデータから生成されたZKP証明を検証
 */

const snarkjs = require('snarkjs');
const fs = require('fs');
const path = require('path');

const KEYS_DIR = path.join(__dirname, '../keys');
const PROOFS_DIR = path.join(__dirname, '../proofs');

async function main() {
    try {
        console.log('🔍 Verifying proof for PCAP CSI data...\n');

        // 証明ファイルとpublic signalsを読み込み
        const proofFile = path.join(PROOFS_DIR, 'csi_pcap_proof.json');
        const publicFile = path.join(PROOFS_DIR, 'csi_pcap_public.json');
        const vkeyFile = path.join(KEYS_DIR, 'csi_subcarrier_selector_verification_key.json');

        const proof = JSON.parse(fs.readFileSync(proofFile, 'utf8'));
        const publicSignals = JSON.parse(fs.readFileSync(publicFile, 'utf8'));
        const vkey = JSON.parse(fs.readFileSync(vkeyFile, 'utf8'));

        // Public signalsを表示
        const bestIndex = parseInt(publicSignals[0]);
        const bestSimilarity = parseInt(publicSignals[1]);
        const hasValidCandidate = parseInt(publicSignals[2]);

        console.log('📤 Public signals:');
        console.log(`  Best Index: ${bestIndex}`);
        console.log(`  Best Similarity: ${bestSimilarity} (${(bestSimilarity/10000).toFixed(4)})`);
        console.log(`  Has Valid Candidate: ${hasValidCandidate} (${hasValidCandidate ? 'YES' : 'NO'})`);

        console.log('\n⚙️  Verifying proof...\n');

        // 証明を検証
        const isValid = await snarkjs.groth16.verify(vkey, publicSignals, proof);

        if (isValid) {
            console.log('============================================================');
            console.log('✅ PROOF VERIFIED SUCCESSFULLY!');
            console.log('   The proof is cryptographically valid.');
            console.log('   CSI subcarrier selection from PCAP data is correct.');
            console.log('============================================================');
        } else {
            console.log('============================================================');
            console.log('❌ PROOF VERIFICATION FAILED!');
            console.log('   The proof is invalid or has been tampered with.');
            console.log('============================================================');
            process.exit(1);
        }

    } catch (error) {
        console.error('\n❌ Error during verification:', error.message);
        process.exit(1);
    }
}

main();
