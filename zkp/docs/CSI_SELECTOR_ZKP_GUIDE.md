# CSI Subcarrier Selector ZKP 証明生成・検証ガイド

## 概要

`csi_subcarrier_selector.circom` 回路を使用して、CSIサブキャリアのコサイン類似度計算のゼロ知識証明を生成・検証します。

## 成功した実行例

### 実行結果
```
✅ 証明生成成功!
✅ 証明検証成功!
```

### 入力データ
- **参照ベクトル**: `[3, 4, 0, 0]` (ノルム = 5)
- **候補1**: `[3, 4, 0, 0]` (ノルム = 5, 類似度 = 1.0000)
- **候補2**: `[4, 3, 0, 0]` (ノルム = 5, 類似度 = 0.9600)

### 出力
- **Best Index**: 1 (候補2が選択された)
- **Best Similarity**: 9600 (0.9600)
- **Has Valid Candidate**: YES

## セットアップと実行手順

### 1. 依存関係のインストール

```bash
cd zkp
npm install
```

### 2. 回路のコンパイル

```bash
node scripts/compile_csi_selector.js
```

**生成されるファイル:**
- `build/csi_subcarrier_selector.r1cs` (73.20 KB)
- `build/csi_subcarrier_selector_js/` (WebAssembly)
- `build/csi_subcarrier_selector.sym`

**回路情報:**
- Template instances: 11
- Non-linear constraints: 430
- Linear constraints: 49
- Public inputs: 12
- Private inputs: 5
- Public outputs: 3

### 3. セットアップ（鍵生成）

```bash
node scripts/setup_csi_selector.js
```

**処理内容:**
1. Powers of Tau ファイルのダウンロード（初回のみ）
2. zKey（proving key）の生成
3. Verification key のエクスポート
4. Solidity verifier contract の生成

**生成されるファイル:**
- `keys/powersOfTau28_hez_final_15.ptau`
- `keys/csi_subcarrier_selector.zkey`
- `keys/csi_subcarrier_selector_verification_key.json`
- `keys/csi_subcarrier_selector_verifier.sol`

### 4. 証明生成

```bash
node scripts/prove_csi_selector.js
```

**実行時間:** 約10秒

**生成されるファイル:**
- `proofs/csi_subcarrier_selector_proof.json`
- `proofs/csi_subcarrier_selector_public.json`

**出力例:**
```
📊 Input data:
  Reference: [3, 4, 0, 0]
  Reference Norm: 5

  Candidate 1: [3, 4, 0, 0]
  Candidate 1 Norm: 5
  Candidate 1 Similarity: 10000 (1.0000)

  Candidate 2: [4, 3, 0, 0]
  Candidate 2 Norm: 5
  Candidate 2 Similarity: 9600 (0.9600)

✅ Proof generation complete!

📤 Public outputs:
  Best Index: 1
  Best Similarity: 9600 (0.9600)
  Has Valid Candidate: 1 (YES)
```

### 5. 証明検証

```bash
node scripts/verify_csi_selector.js
```

**実行時間:** 約2秒

**成功時の出力:**
```
============================================================
✅ PROOF VERIFIED SUCCESSFULLY!
   The proof is cryptographically valid.
   CSI subcarrier selection computation is correct.
============================================================
```

## ワンライナー実行

```bash
cd zkp && \
npm install && \
node scripts/compile_csi_selector.js && \
node scripts/setup_csi_selector.js && \
node scripts/prove_csi_selector.js && \
node scripts/verify_csi_selector.js
```

## 回路の仕様

### 入力パラメータ

| パラメータ | 型 | 説明 |
|-----------|-----|------|
| `reference[4]` | signal input | 参照CSIベクトル |
| `candidates[2][4]` | signal input | 候補CSIベクトル群（2候補） |
| `referenceNorm` | signal input | 参照ベクトルのノルム |
| `candidateNorms[2]` | signal input | 各候補のノルム |
| `similarities[2]` | signal input | 各候補の類似度 |

### 出力パラメータ

| パラメータ | 型 | 説明 |
|-----------|-----|------|
| `bestIndex` | signal output | 最も類似度が高い候補のインデックス |
| `bestSimilarity` | signal output | 最大類似度 |
| `hasValidCandidate` | signal output | 閾値以上の候補が存在する場合1 |

### 回路の制約条件

1. **ノルムの検証**: `normA² === normA_squared`（回路内で計算）
2. **類似度の検証**: `similarity × normA × normB === dotProduct × SCALE`
3. **閾値判定**: `similarity >= THRESHOLD` (7000 = 0.7)
4. **ゼロベクトルチェック**: `normA > 0 && normB > 0`

### 固定小数点演算

- **スケール**: 10000
- 例: 類似度 0.9600 → 9600
- 例: 閾値 0.7 → 7000

## 重要な注意事項

### ベクトル値の制約

**回路が正常に動作するには、ノルムが整数になるベクトルを使用する必要があります。**

✅ **動作する例:**
- `[3, 4, 0, 0]` → ノルム = 5 (√(9+16) = 5)
- `[5, 12, 0, 0]` → ノルム = 13 (√(25+144) = 13)
- `[8, 15, 0, 0]` → ノルム = 17 (√(64+225) = 17)

❌ **動作しない例:**
- `[1, 2, 3, 4]` → ノルム = 5.477... (整数でない)
- `[10, 20, 30, 40]` → ノルム = 54.77... (整数でない)

### 理由

回路内で `normA² === normA_squared` という厳密な制約があるため:
- `normA = floor(sqrt(sumSquares))` の場合
- `normA² != sumSquares` となり制約違反

## カスタム入力データの使用

`prove_csi_selector.js` を編集してカスタムデータを使用できます:

```javascript
// ピタゴラス数を使用した例
const reference = [3, 4, 0, 0];  // ノルム = 5
const candidates = [
    [5, 12, 0, 0],   // ノルム = 13
    [8, 15, 0, 0]    // ノルム = 17
];
```

### ピタゴラス数の例

| a | b | c (ノルム) |
|---|---|-----------|
| 3 | 4 | 5 |
| 5 | 12 | 13 |
| 8 | 15 | 17 |
| 7 | 24 | 25 |
| 20 | 21 | 29 |

## トラブルシューティング

### Assert Failed エラー

```
ERROR: 4 Error in template CosineSimilarityVerified line: 117
```

**原因**: ノルムが整数でないベクトルを使用している

**解決策**: ピタゴラス数を使用したベクトルに変更

### Non quadratic constraints エラー

```
ERROR: Non quadratic constraints are not allowed!
```

**原因**: 回路内で3つ以上の変数の乗算を使用

**解決策**: 中間変数を使って二次制約に分解（既に修正済み）

### コンパイルエラー

```bash
# 再コンパイル
rm -rf build/csi_subcarrier_selector*
node scripts/compile_csi_selector.js
```

## ファイル構造

```
zkp/
├── circuits/
│   └── csi_subcarrier_selector.circom  # 回路定義
├── scripts/
│   ├── compile_csi_selector.js         # コンパイル
│   ├── setup_csi_selector.js           # セットアップ
│   ├── prove_csi_selector.js           # 証明生成
│   └── verify_csi_selector.js          # 証明検証
├── build/                               # コンパイル出力
├── keys/                                # 鍵ファイル
├── proofs/                              # 証明ファイル
└── CSI_SELECTOR_ZKP_GUIDE.md           # このガイド
```

## パフォーマンス

- **コンパイル時間**: 約1秒
- **セットアップ時間**: 約30秒（初回は+ダウンロード時間）
- **証明生成時間**: 約10秒
- **証明検証時間**: 約2秒

## 参考情報

- [circom Documentation](https://docs.circom.io/)
- [snarkjs Documentation](https://github.com/iden3/snarkjs)
- [Groth16 Protocol](https://eprint.iacr.org/2016/260.pdf)
- [Pythagorean Triples](https://en.wikipedia.org/wiki/Pythagorean_triple)
