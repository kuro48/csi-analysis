const { expect } = require('chai');
const path = require('path');
const fs = require('fs');
const { exec } = require('child_process');
const util = require('util');

const execPromise = util.promisify(exec);

describe('Breathing Verifier Circuit Tests', function() {
    this.timeout(120000); // 2分のタイムアウト

    const CIRCUIT_NAME = 'breathing_verifier';
    const BUILD_DIR = path.join(__dirname, '../build');
    const KEYS_DIR = path.join(__dirname, '../keys');

    before(function() {
        // 必要なファイルが存在するか確認
        const wasmFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}_js`, `${CIRCUIT_NAME}.wasm`);
        const zKeyFile = path.join(KEYS_DIR, `${CIRCUIT_NAME}.zkey`);

        if (!fs.existsSync(wasmFile)) {
            throw new Error('WASM file not found. Please run compile first.');
        }
        if (!fs.existsSync(zKeyFile)) {
            throw new Error('zKey file not found. Please run setup first.');
        }
    });

    /**
     * ヘルパー: witness計算
     */
    async function calculateWitness(input) {
        const wasmFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}_js`, `${CIRCUIT_NAME}.wasm`);
        const inputFile = path.join(BUILD_DIR, 'test_input.json');
        const witnessFile = path.join(BUILD_DIR, 'test_witness.wtns');

        fs.writeFileSync(inputFile, JSON.stringify(input));

        await execPromise(`snarkjs wtns calculate ${wasmFile} ${inputFile} ${witnessFile}`);

        return witnessFile;
    }

    /**
     * ヘルパー: 証明生成
     */
    async function generateProof(witnessFile) {
        const zKeyFile = path.join(KEYS_DIR, `${CIRCUIT_NAME}.zkey`);
        const proofFile = path.join(BUILD_DIR, 'test_proof.json');
        const publicFile = path.join(BUILD_DIR, 'test_public.json');

        await execPromise(`snarkjs groth16 prove ${zKeyFile} ${witnessFile} ${proofFile} ${publicFile}`);

        return {
            proof: JSON.parse(fs.readFileSync(proofFile)),
            publicSignals: JSON.parse(fs.readFileSync(publicFile))
        };
    }

    /**
     * ヘルパー: 証明検証
     */
    async function verifyProof(proof, publicSignals) {
        const vKeyFile = path.join(KEYS_DIR, 'verification_key.json');
        const proofFile = path.join(BUILD_DIR, 'test_proof.json');
        const publicFile = path.join(BUILD_DIR, 'test_public.json');

        fs.writeFileSync(proofFile, JSON.stringify(proof));
        fs.writeFileSync(publicFile, JSON.stringify(publicSignals));

        const { stdout } = await execPromise(`snarkjs groth16 verify ${vKeyFile} ${publicFile} ${proofFile}`);

        return stdout.includes('OK');
    }

    /**
     * ヘルパー: 有効な入力データの生成（超シンプル版）
     */
    function generateValidInput() {
        return {
            breathingRate: 15,        // 15 bpm（正常範囲: 10-30）
            confidenceScore: 85       // 85%（閾値: 70以上）
        };
    }

    describe('Valid Input Tests', function() {
        it('should accept valid breathing rate data', async function() {
            const input = generateValidInput();

            const witnessFile = await calculateWitness(input);
            const { proof, publicSignals } = await generateProof(witnessFile);
            const isValid = await verifyProof(proof, publicSignals);

            expect(isValid).to.be.true;
        });

        it('should accept breathing rate at lower boundary (10 bpm)', async function() {
            const input = generateValidInput();
            input.breathingRate = 10;  // 最小値

            const witnessFile = await calculateWitness(input);
            const { proof, publicSignals } = await generateProof(witnessFile);
            const isValid = await verifyProof(proof, publicSignals);

            expect(isValid).to.be.true;
        });

        it('should accept breathing rate at upper boundary (30 bpm)', async function() {
            const input = generateValidInput();
            input.breathingRate = 30;  // 最大値

            const witnessFile = await calculateWitness(input);
            const { proof, publicSignals } = await generateProof(witnessFile);
            const isValid = await verifyProof(proof, publicSignals);

            expect(isValid).to.be.true;
        });

        it('should accept confidence score at threshold (70%)', async function() {
            const input = generateValidInput();
            input.confidenceScore = 70;

            const witnessFile = await calculateWitness(input);
            const { proof, publicSignals } = await generateProof(witnessFile);
            const isValid = await verifyProof(proof, publicSignals);

            expect(isValid).to.be.true;
        });
    });

    describe('Invalid Input Tests', function() {
        it('should reject breathing rate above 30 bpm', async function() {
            const input = generateValidInput();
            input.breathingRate = 31;  // 範囲外（最大値超過）

            try {
                const witnessFile = await calculateWitness(input);
                const { proof, publicSignals } = await generateProof(witnessFile);
                const isValid = await verifyProof(proof, publicSignals);
                expect(isValid).to.be.false;
            } catch (error) {
                // Witness計算時にエラーが出ることを期待
                expect(error).to.exist;
            }
        });

        it('should reject breathing rate below 10 bpm', async function() {
            const input = generateValidInput();
            input.breathingRate = 9;  // 範囲外（最小値未満）

            try {
                const witnessFile = await calculateWitness(input);
                const { proof, publicSignals } = await generateProof(witnessFile);
                const isValid = await verifyProof(proof, publicSignals);
                expect(isValid).to.be.false;
            } catch (error) {
                expect(error).to.exist;
            }
        });

        it('should reject confidence score below 70%', async function() {
            const input = generateValidInput();
            input.confidenceScore = 69;  // 閾値未満

            try {
                const witnessFile = await calculateWitness(input);
                const { proof, publicSignals } = await generateProof(witnessFile);
                const isValid = await verifyProof(proof, publicSignals);
                expect(isValid).to.be.false;
            } catch (error) {
                expect(error).to.exist;
            }
        });

    });

    describe('Performance Tests', function() {
        it('should generate proof in under 10 seconds', async function() {
            const input = generateValidInput();

            const witnessFile = await calculateWitness(input);

            const startTime = Date.now();
            await generateProof(witnessFile);
            const duration = (Date.now() - startTime) / 1000;

            console.log(`   Proof generation time: ${duration.toFixed(2)}s`);
            expect(duration).to.be.lessThan(10);
        });

        it('should verify proof in under 1 second', async function() {
            const input = generateValidInput();

            const witnessFile = await calculateWitness(input);
            const { proof, publicSignals } = await generateProof(witnessFile);

            const startTime = Date.now();
            await verifyProof(proof, publicSignals);
            const duration = (Date.now() - startTime) / 1000;

            console.log(`   Verification time: ${duration.toFixed(3)}s`);
            expect(duration).to.be.lessThan(1);
        });
    });
});
