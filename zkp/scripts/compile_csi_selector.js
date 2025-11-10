/**
 * CSIサブキャリア選択回路のコンパイルスクリプト
 */

const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const util = require('util');

const execPromise = util.promisify(exec);

// パス設定
const CIRCUITS_DIR = path.join(__dirname, '..', 'circuits');
const BUILD_DIR = path.join(__dirname, '..', 'build');
const CIRCUIT_NAME = 'csi_subcarrier_selector';
const CIRCUIT_FILE = path.join(CIRCUITS_DIR, `${CIRCUIT_NAME}.circom`);

// ビルドディレクトリ作成
if (!fs.existsSync(BUILD_DIR)) {
    fs.mkdirSync(BUILD_DIR, { recursive: true });
}

/**
 * コマンド実行ヘルパー
 */
async function runCommand(command, description) {
    console.log(`\n[${new Date().toISOString()}] ${description}...`);
    console.log(`実行コマンド: ${command}`);

    try {
        const { stdout, stderr } = await execPromise(command);
        if (stdout) console.log(stdout);
        if (stderr) console.error(stderr);
        console.log(`✓ ${description} 完了`);
        return true;
    } catch (error) {
        console.error(`✗ ${description} 失敗:`);
        console.error(error.message);
        if (error.stdout) console.log(error.stdout);
        if (error.stderr) console.error(error.stderr);
        return false;
    }
}

/**
 * Circom回路のコンパイル
 */
async function compileCircuit() {
    const outputDir = BUILD_DIR;

    const command = `circom ${CIRCUIT_FILE} --r1cs --wasm --sym -o ${outputDir}`;

    const success = await runCommand(
        command,
        'Circom回路コンパイル'
    );

    if (success) {
        console.log('\n生成されたファイル:');
        console.log(`  - ${path.join(outputDir, CIRCUIT_NAME + '.r1cs')} (制約システム)`);
        console.log(`  - ${path.join(outputDir, CIRCUIT_NAME + '_js', CIRCUIT_NAME + '.wasm')} (witness計算用WASM)`);
        console.log(`  - ${path.join(outputDir, CIRCUIT_NAME + '.sym')} (シンボル情報)`);
    }

    return success;
}

/**
 * R1CS情報の表示
 */
async function showR1CSInfo() {
    const r1csFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}.r1cs`);

    const command = `snarkjs r1cs info ${r1csFile}`;

    await runCommand(command, 'R1CS情報表示');
}

/**
 * R1CSのエクスポート (デバッグ用)
 */
async function exportR1CS() {
    const r1csFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}.r1cs`);
    const jsonFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}.r1cs.json`);

    const command = `snarkjs r1cs export json ${r1csFile} ${jsonFile}`;

    const success = await runCommand(command, 'R1CSのJSON出力');

    if (success) {
        console.log(`JSON出力: ${jsonFile}`);
    }

    return success;
}

/**
 * 回路の制約数とサイズ分析
 */
async function analyzeCircuit() {
    const r1csFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}.r1cs`);

    if (!fs.existsSync(r1csFile)) {
        console.error('R1CSファイルが見つかりません。先にコンパイルしてください。');
        return;
    }

    console.log('\n===== 回路分析 =====');

    // ファイルサイズ
    const stats = fs.statSync(r1csFile);
    console.log(`R1CSファイルサイズ: ${(stats.size / 1024).toFixed(2)} KB`);

    // R1CS詳細情報
    await showR1CSInfo();
}

/**
 * メイン実行
 */
async function main() {
    console.log('==========================================');
    console.log('CSIサブキャリア選択回路 コンパイル');
    console.log('==========================================');

    // 1. Circom回路コンパイル
    const compileSuccess = await compileCircuit();
    if (!compileSuccess) {
        console.error('\nコンパイル失敗。処理を中断します。');
        process.exit(1);
    }

    // 2. 回路分析
    await analyzeCircuit();

    // 3. R1CSエクスポート (オプション)
    if (process.argv.includes('--export-json')) {
        await exportR1CS();
    }

    console.log('\n==========================================');
    console.log('コンパイル完了 ✓');
    console.log('==========================================');

    console.log('\n次のステップ:');
    console.log('1. テスト実行: node scripts/test_csi_selector.js');
    console.log('2. Witness生成: node build/csi_subcarrier_selector_js/generate_witness.js ...');
    console.log('3. 証明生成: snarkjs groth16 prove ...');
}

// スクリプト実行
if (require.main === module) {
    main().catch(error => {
        console.error('エラー発生:', error);
        process.exit(1);
    });
}

module.exports = {
    compileCircuit,
    analyzeCircuit
};
