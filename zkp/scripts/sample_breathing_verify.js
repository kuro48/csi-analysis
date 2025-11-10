const snarkjs = require('snarkjs');
const fs = require('fs');
const path = require('path');

async function main() {
    console.log('🔍 Sample Breathing Proof Verification\n');

    const proofPath = path.join(__dirname, '../build/sample_breathing_proof.json');
    const publicPath = path.join(__dirname, '../build/sample_breathing_public.json');
    const vKeyPath = path.join(__dirname, '../keys/sample_breathing_vkey.json');

    if (!fs.existsSync(proofPath) || !fs.existsSync(publicPath)) {
        console.error('❌ Error: Proof files not found!');
        console.error('   Please run sample_breathing_prove.js first');
        process.exit(1);
    }

    const proof = JSON.parse(fs.readFileSync(proofPath, 'utf8'));
    const publicSignals = JSON.parse(fs.readFileSync(publicPath, 'utf8'));
    const vKey = JSON.parse(fs.readFileSync(vKeyPath, 'utf8'));

    console.log('📋 Public Signals:');
    console.log(`   isValid: ${publicSignals[0]}`);
    console.log(`   ${publicSignals[0] === '1' ? '✅ Claims: Within valid range' : '❌ Claims: Out of range'}\n`);

    console.log('🔐 Verifying proof...');

    const isValid = await snarkjs.groth16.verify(vKey, publicSignals, proof);

    console.log('\n' + '='.repeat(50));
    if (isValid) {
        console.log('✅ PROOF IS VALID!');
    } else {
        console.log('❌ PROOF IS INVALID!');
        console.log('\n⚠️  The proof verification failed.');
    }
    console.log('='.repeat(50) + '\n');
}

main()
    .then(() => { process.exit(0); })
    .catch((err) => { console.error('❌ Error:', err.message); process.exit(1); });
