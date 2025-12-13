#!/usr/bin/env node
/**
 * Poseidonハッシュを計算するヘルパースクリプト
 *
 * 使い方: node scripts/poseidon_hash.js /path/to/input.json
 * input.json は文字列または数値の配列（BigIntに変換して計算）
 * 標準出力に10進文字列でハッシュ値を返す
 */

const fs = require('fs');
const path = require('path');

function main() {
  const inputPath = process.argv[2];
  if (!inputPath) {
    console.error('Usage: node poseidon_hash.js <input.json>');
    process.exit(1);
  }

  const resolvedPath = path.resolve(process.cwd(), inputPath);
  if (!fs.existsSync(resolvedPath)) {
    console.error(`Input file not found: ${resolvedPath}`);
    process.exit(1);
  }

  let values;
  try {
    values = JSON.parse(fs.readFileSync(resolvedPath, 'utf8'));
  } catch (e) {
    console.error(`Failed to read input JSON: ${e.message}`);
    process.exit(1);
  }

  if (!Array.isArray(values)) {
    console.error('Input must be a JSON array');
    process.exit(1);
  }

  // circomlib の Poseidon
  const { poseidon } = require('circomlib');
  const F = poseidon.F;

  const inputs = values.map((v) => BigInt(v));
  const hash = poseidon(inputs);
  const hashStr = F.toString(hash); // 10進文字列

  process.stdout.write(hashStr);
}

main();
