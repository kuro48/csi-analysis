# CSIサブキャリア選択回路 - クイックスタートガイド

Wi-Fi CSI測定におけるサブキャリア選択をゼロ知識証明回路で実装したプロジェクトです。

## 🎯 主な機能

- ✅ **コサイン類似度計算**: 固定小数点演算による高精度計算
- ✅ **ゼロ知識証明**: プライバシー保護しながら計算結果を検証
- ✅ **リアルタイム処理**: 最適化された回路設計で低レイテンシ実現
- ✅ **柔軟なパラメータ**: ベクトル次元・候補数・閾値をカスタマイズ可能

## 📁 プロジェクト構成

```
zkp/
├── circuits/
│   ├── csi_subcarrier_selector.circom  # メイン回路
│   ├── cosine_similarity.circom        # 基本的なコサイン類似度回路
│   ├── breathing_verifier.circom       # 呼吸数検証回路(既存)
│   └── README_CSI_Selector.md          # 技術詳細ドキュメント
├── scripts/
│   ├── test_csi_selector.js            # テスト&Witness生成スクリプト
│   ├── compile_csi_selector.js         # コンパイルスクリプト
│   ├── compile.js                      # 汎用コンパイルスクリプト
│   ├── setup.js                        # セットアップスクリプト
│   ├── prove.js                        # 証明生成スクリプト
│   └── verify.js                       # 検証スクリプト
├── build/                              # コンパイル済みファイル (自動生成)
├── package.json                        # 依存関係管理
└── README_CSI_Integration.md           # このファイル
```

## 🚀 クイックスタート

### 1. 環境セットアップ

```bash
# Node.js依存関係をインストール
npm install

# Circomコンパイラインストール (未インストールの場合)
# https://docs.circom.io/getting-started/installation/
```

### 2. テスト実行

```bash
# コサイン類似度計算のテスト
node scripts/test_csi_selector.js
```

**期待される出力**:
```
==========================================
CSIサブキャリア選択回路テスト
==========================================

===== テストケース1: 同一ベクトル =====
期待される類似度: 1.000000
固定小数点計算結果: 1.000000
...

===== テストケース4: サブキャリア選択 =====
候補1の類似度: 0.998954
候補2の類似度: 0.828053
選択されるべき候補: 候補1

Witness JSONファイルを生成: .../csi_selector_witness.json

==========================================
全テスト完了 ✓
==========================================
```

### 3. 回路コンパイル

```bash
# CSI選択回路をコンパイル
node scripts/compile_csi_selector.js

# または手動でコンパイル
circom circuits/csi_subcarrier_selector.circom --r1cs --wasm --sym -o build/
```

**生成されるファイル**:
- `build/csi_subcarrier_selector.r1cs` - 制約システム
- `build/csi_subcarrier_selector_js/csi_subcarrier_selector.wasm` - Witness計算用
- `build/csi_subcarrier_selector.sym` - シンボル情報

### 4. ゼロ知識証明の生成と検証

#### 4.1 セットアップ (初回のみ)

```bash
# Powers of Tau ダウンロード (約35MB)
wget https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_12.ptau

# 信頼されたセットアップ
snarkjs groth16 setup \
  build/csi_subcarrier_selector.r1cs \
  powersOfTau28_hez_final_12.ptau \
  build/csi_selector_0000.zkey

# 検証キー生成
snarkjs zkey export verificationkey \
  build/csi_selector_0000.zkey \
  build/verification_key.json
```

#### 4.2 Witness生成

```bash
cd build/csi_subcarrier_selector_js

# テストスクリプトで生成したwitness JSONを使用
node generate_witness.js \
  csi_subcarrier_selector.wasm \
  ../../csi_selector_witness.json \
  witness.wtns
```

#### 4.3 証明生成

```bash
snarkjs groth16 prove \
  build/csi_selector_0000.zkey \
  build/csi_subcarrier_selector_js/witness.wtns \
  build/proof.json \
  build/public.json
```

#### 4.4 検証

```bash
snarkjs groth16 verify \
  build/verification_key.json \
  build/public.json \
  build/proof.json
```

**成功時の出力**:
```
[INFO]  snarkJS: OK!
```

## 📊 パラメータ設定

### 回路パラメータ

`circuits/csi_subcarrier_selector.circom` の最終行で設定:

```circom
component main {public [reference, candidates]} =
  CSISubcarrierSelector(N, M, SCALE, THRESHOLD);
```

| パラメータ | デフォルト | 説明 |
|------------|-----------|------|
| N          | 4         | ベクトル次元数 (サブキャリア数) |
| M          | 2         | 候補数 |
| SCALE      | 10000     | 固定小数点スケール (10^4) |
| THRESHOLD  | 7000      | 選択閾値 (0.7 = 70%) |

### 推奨設定

**低レイテンシ優先** (エッジデバイス):
```circom
CSISubcarrierSelector(4, 2, 10000, 6500)
// N=4: 高速, M=2: 2候補比較, 閾値0.65
```

**高精度優先** (サーバーサイド):
```circom
CSISubcarrierSelector(8, 4, 100000, 7500)
// N=8: 高精度, M=4: 4候補比較, 閾値0.75, スケール10^5
```

## 🔧 カスタマイズ

### 入力データフォーマット

Witness JSON形式:

```json
{
  "reference": [8500, 6200, 4800, 3100],
  "candidates": [
    [8200, 6500, 4500, 3300],
    [4500, 3000, 8500, 6000]
  ],
  "referenceNorm": 11747,
  "candidateNorms": [11831, 11489],
  "similarities": [9990, 8281]
}
```

**データ変換**:

```javascript
const SCALE = 10000;

// 実数 → 固定小数点
const toFixedPoint = (value) => Math.round(value * SCALE);

// CSIデータの正規化
const normalizeCSI = (csiData) => {
  const max = Math.max(...csiData.map(Math.abs));
  return csiData.map(v => v / max);
};

// 使用例
const rawCSI = [42.5, 31.8, 24.3, 15.7];  // 生CSIデータ
const normalized = normalizeCSI(rawCSI);   // [1.0, 0.748, 0.571, 0.369]
const fixedPoint = normalized.map(toFixedPoint);  // [10000, 7480, 5710, 3690]
```

### 閾値の動的調整

環境ノイズに応じて閾値を調整:

```javascript
function adaptiveThreshold(noiseLevel) {
  const baseThreshold = 0.7;
  const noiseFactor = noiseLevel / 100;  // 0-1の範囲
  const adjustedThreshold = baseThreshold - (noiseFactor * 0.2);

  return Math.round(adjustedThreshold * SCALE);
}

// 使用例
const threshold = adaptiveThreshold(30);  // ノイズレベル30%
// threshold = 6400 (0.64)
```

## 🧪 デバッグ

### ログ出力の有効化

```bash
# 詳細ログ付きでテスト実行
DEBUG=* node scripts/test_csi_selector.js
```

### 制約数の確認

```bash
# R1CS情報表示
snarkjs r1cs info build/csi_subcarrier_selector.r1cs
```

### Witness計算のデバッグ

```javascript
// scripts/test_csi_selector.js 内で
console.log('Debug - DotProduct:', dotProduct);
console.log('Debug - NormA:', normA, 'NormB:', normB);
console.log('Debug - Similarity (raw):', similarity);
console.log('Debug - Similarity (scaled):', similarity / SCALE);
```

## 📈 パフォーマンス

### ベンチマーク結果

測定環境: MacBook Pro M1, 16GB RAM

| 操作 | 時間 |
|------|------|
| テストスクリプト実行 | ~50ms |
| 回路コンパイル | ~2s |
| Witness生成 | ~20ms |
| 証明生成 | ~500ms |
| 検証 | ~5ms |

### 最適化のヒント

1. **ベクトル次元の最小化**: N=4で十分な精度が得られる場合が多い
2. **候補数の制限**: M=2-4が実用的
3. **witness計算の並列化**: 複数候補を並列処理
4. **キャッシング**: 参照ベクトルのノルムをキャッシュ

## 🔗 統合例

### エッジデバイスとの統合

```javascript
// エッジデバイスからのCSIデータ受信
const csiData = await fetchCSIFromDevice();

// サブキャリア選択
const { calculateCosineSimilarity, toFixedPoint } = require('./scripts/test_csi_selector');

const reference = csiData.referencePattern;
const candidates = csiData.subcarriers;

const similarities = candidates.map(candidate =>
  calculateCosineSimilarity(reference, candidate)
);

const bestIndex = similarities.indexOf(Math.max(...similarities));
console.log(`最適サブキャリア: インデックス ${bestIndex}`);
```

### バックエンドAPIとの統合

```javascript
// FastAPI (Python) での例
// POST /api/v2/csi-data/select-subcarrier

const { spawn } = require('child_process');

async function selectSubcarrierWithZKP(csiData) {
  // Witness生成
  const witness = generateWitness(csiData);

  // ZKP証明生成
  const proof = await generateProof(witness);

  // 検証
  const isValid = await verifyProof(proof);

  return {
    selectedIndex: witness.bestIndex,
    similarity: witness.maxSimilarity,
    proofValid: isValid
  };
}
```

## 📚 関連ドキュメント

- [技術詳細ドキュメント](./circuits/README_CSI_Selector.md) - 数学的背景と実装詳細
- [Circom公式ドキュメント](https://docs.circom.io/)
- [snarkjs公式ドキュメント](https://github.com/iden3/snarkjs)

## 🐛 トラブルシューティング

### エラー: `circom: command not found`

**解決策**: Circomコンパイラをインストール
```bash
# macOS (Homebrew)
brew install circom

# または公式インストーラー
curl --proto '=https' --tlsv1.2 https://sh.rustup.rs -sSf | sh
cargo install circom
```

### エラー: `Error: Cannot find module 'snarkjs'`

**解決策**: snarkjsをグローバルインストール
```bash
npm install -g snarkjs
```

### エラー: `Constraint doesn't match`

**原因**: Witness計算の精度問題

**解決策**:
1. スケールを調整 (10^4 → 10^3)
2. 丸め処理を追加
3. 許容誤差を設定

```javascript
// 丸め処理を追加
const similarity = Math.round((dotProduct * SCALE) / (normA * normB));
```

## 🤝 コントリビューション

改善提案やバグ報告は Issues にてお願いします。

## 📄 ライセンス

MIT License

---

**バージョン**: 1.0.0
**最終更新**: 2025-01-10
**メンテナー**: CSI Web Platform Team
