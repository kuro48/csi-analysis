#!/usr/bin/env node

/**
 * CSI Subcarrier Selector ZKP証明システムのセットアップスクリプト
 */

const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const https = require('https');

const CIRCUIT_NAME = 'csi_subcarrier_selector';
const BUILD_DIR = path.join(__dirname, '../build');
const KEYS_DIR = path.join(__dirname, '../keys');

// ディレクトリの作成
if (!fs.existsSync(KEYS_DIR)) {
    fs.mkdirSync(KEYS_DIR, { recursive: true });
}

const PTAU_FILE = path.join(KEYS_DIR, 'powersOfTau28_hez_final_15.ptau');
const PTAU_URL = 'https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_15.ptau';

function downloadPowerOfTau() {
    return new Promise((resolve, reject) => {
        if (fs.existsSync(PTAU_FILE)) {
            console.log('✓ Powers of Tau file already exists, skipping download');
            resolve();
            return;
        }

        console.log('📥 Downloading Powers of Tau ceremony file...');
        console.log('   This may take several minutes (200+ MB)');

        const file = fs.createWriteStream(PTAU_FILE);
        https.get(PTAU_URL, (response) => {
            const totalBytes = parseInt(response.headers['content-length'], 10);
            let downloadedBytes = 0;

            response.on('data', (chunk) => {
                downloadedBytes += chunk.length;
                const progress = ((downloadedBytes / totalBytes) * 100).toFixed(1);
                process.stdout.write(`\r   Progress: ${progress}% (${(downloadedBytes / 1024 / 1024).toFixed(1)} MB)`);
            });

            response.pipe(file);

            file.on('finish', () => {
                file.close();
                console.log('\n✅ Powers of Tau download complete!');
                resolve();
            });
        }).on('error', (err) => {
            fs.unlink(PTAU_FILE, () => {});
            reject(err);
        });
    });
}

function generateZKey() {
    return new Promise((resolve, reject) => {
        const r1csFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}.r1cs`);
        const zKeyFile = path.join(KEYS_DIR, `${CIRCUIT_NAME}.zkey`);

        if (!fs.existsSync(r1csFile)) {
            reject(new Error('R1CS file not found. Please run compile_csi_selector.js first.'));
            return;
        }

        console.log('\n🔑 Generating zKey (proving key)...');

        const zkeyCmd = `npx snarkjs groth16 setup ${r1csFile} ${PTAU_FILE} ${zKeyFile}`;

        exec(zkeyCmd, (error, stdout, stderr) => {
            if (error) {
                console.error('❌ zKey generation failed:');
                console.error(stderr);
                reject(error);
                return;
            }

            console.log('✅ zKey generation complete!');
            resolve(zKeyFile);
        });
    });
}

function exportVerificationKey(zKeyFile) {
    return new Promise((resolve, reject) => {
        const vKeyFile = path.join(KEYS_DIR, `${CIRCUIT_NAME}_verification_key.json`);

        console.log('\n🔐 Exporting verification key...');

        const exportCmd = `npx snarkjs zkey export verificationkey ${zKeyFile} ${vKeyFile}`;

        exec(exportCmd, (error, stdout, stderr) => {
            if (error) {
                console.error('❌ Verification key export failed:');
                console.error(stderr);
                reject(error);
                return;
            }

            console.log('✅ Verification key exported!');
            console.log(`   Location: ${vKeyFile}`);
            resolve(vKeyFile);
        });
    });
}

function generateSolidityVerifier(zKeyFile) {
    return new Promise((resolve, reject) => {
        const verifierFile = path.join(KEYS_DIR, `${CIRCUIT_NAME}_verifier.sol`);

        console.log('\n📜 Generating Solidity verifier contract...');

        const solidityCmd = `npx snarkjs zkey export solidityverifier ${zKeyFile} ${verifierFile}`;

        exec(solidityCmd, (error, stdout, stderr) => {
            if (error) {
                console.error('❌ Solidity verifier generation failed:');
                console.error(stderr);
                reject(error);
                return;
            }

            console.log('✅ Solidity verifier generated!');
            console.log(`   Location: ${verifierFile}`);
            resolve(verifierFile);
        });
    });
}

async function main() {
    try {
        console.log('🚀 Starting CSI Subcarrier Selector ZKP setup...\n');

        await downloadPowerOfTau();
        const zKeyFile = await generateZKey();
        await exportVerificationKey(zKeyFile);
        await generateSolidityVerifier(zKeyFile);

        console.log('\n✅ Setup complete! Ready to generate and verify proofs.');

    } catch (error) {
        console.error('\n❌ Setup failed:', error.message);
        process.exit(1);
    }
}

main();
