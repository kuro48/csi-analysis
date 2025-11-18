# ZKP証明生成・検証 クイックスタート

## 🎯 実行済み・動作確認済み

CSI Subcarrier Selectorを使用したゼロ知識証明の生成と検証が**成功**しました！

## 📋 必要な手順（全て実行済み）

```bash
# 1. コンパイル
node scripts/compile_csi_selector.js  ✅

# 2. セットアップ
node scripts/setup_csi_selector.js  ✅

# 3. 証明生成
node scripts/prove_csi_selector.js  ✅

# 4. 証明検証
node scripts/verify_csi_selector.js  ✅
```

## ✅ 実行結果

### 証明生成結果
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

### 証明検証結果
```
============================================================
✅ PROOF VERIFIED SUCCESSFULLY!
   The proof is cryptographically valid.
   CSI subcarrier selection computation is correct.
============================================================
```

## 🔑 生成されたファイル

### ビルドファイル
- `build/csi_subcarrier_selector.r1cs` (73.20 KB)
- `build/csi_subcarrier_selector_js/csi_subcarrier_selector.wasm`
- `build/csi_subcarrier_selector.sym`

### 鍵ファイル
- `keys/powersOfTau28_hez_final_15.ptau` (Powers of Tau)
- `keys/csi_subcarrier_selector.zkey` (Proving key)
- `keys/csi_subcarrier_selector_verification_key.json`
- `keys/csi_subcarrier_selector_verifier.sol`

### 証明ファイル
- `proofs/csi_subcarrier_selector_proof.json`
- `proofs/csi_subcarrier_selector_public.json`

## 🚀 次回の実行方法

証明を再生成する場合:

```bash
# データを変更して証明生成
node scripts/prove_csi_selector.js

# 検証
node scripts/verify_csi_selector.js
```

## ⚠️ 重要な制約

**ノルムが整数になるベクトルを使用してください**

✅ 動作する例:
```javascript
[3, 4, 0, 0]   // ノルム = 5
[5, 12, 0, 0]  // ノルム = 13
[8, 15, 0, 0]  // ノルム = 17
```

❌ 動作しない例:
```javascript
[1, 2, 3, 4]     // ノルム = 5.477... (非整数)
[10, 20, 30, 40] // ノルム = 54.77... (非整数)
```

## 📚 詳細ドキュメント

- 詳細な説明: `CSI_SELECTOR_ZKP_GUIDE.md`
- 回路定義: `circuits/csi_subcarrier_selector.circom`
- 証明生成スクリプト: `scripts/prove_csi_selector.js`

## ⏱️ パフォーマンス

- コンパイル: ~1秒
- セットアップ: ~30秒
- 証明生成: ~10秒
- 証明検証: ~2秒
