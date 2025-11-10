#!/usr/bin/env node

/**
 * circom回路のコンパイルスクリプト
 * breathing_verifier.circom をコンパイルして r1cs, wasm, sym ファイルを生成
 */

const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');

const CIRCUIT_NAME = 'breathing_verifier';
const CIRCUITS_DIR = path.join(__dirname, '../circuits');
const BUILD_DIR = path.join(__dirname, '../build');

// ビルドディレクトリの作成
if (!fs.existsSync(BUILD_DIR)) {
    fs.mkdirSync(BUILD_DIR, { recursive: true });
}

console.log('🔧 Compiling circom circuit...');
console.log(`Circuit: ${CIRCUIT_NAME}.circom`);
console.log(`Output: ${BUILD_DIR}`);

// circom コンパイルコマンド
const compileCmd = `circom ${path.join(CIRCUITS_DIR, CIRCUIT_NAME + '.circom')} \
    --r1cs \
    --wasm \
    --sym \
    -o ${BUILD_DIR}`;

exec(compileCmd, (error, stdout, stderr) => {
    if (error) {
        console.error('❌ Compilation failed:');
        console.error(stderr);
        process.exit(1);
    }

    console.log('✅ Compilation successful!');
    console.log(stdout);

    // 生成されたファイルの確認
    const r1csFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}.r1cs`);
    const wasmDir = path.join(BUILD_DIR, `${CIRCUIT_NAME}_js`);
    const symFile = path.join(BUILD_DIR, `${CIRCUIT_NAME}.sym`);

    console.log('\n📁 Generated files:');
    if (fs.existsSync(r1csFile)) {
        const stats = fs.statSync(r1csFile);
        console.log(`  ✓ ${CIRCUIT_NAME}.r1cs (${(stats.size / 1024).toFixed(2)} KB)`);
    }
    if (fs.existsSync(wasmDir)) {
        console.log(`  ✓ ${CIRCUIT_NAME}_js/ (WebAssembly)`);
    }
    if (fs.existsSync(symFile)) {
        console.log(`  ✓ ${CIRCUIT_NAME}.sym`);
    }

    // 回路情報の表示
    const infoCmd = `snarkjs r1cs info ${r1csFile}`;
    exec(infoCmd, (error, stdout, stderr) => {
        if (!error) {
            console.log('\n📊 Circuit Information:');
            console.log(stdout);
        }
    });
});
