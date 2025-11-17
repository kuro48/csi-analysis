# ZKP回路 整理サマリー

## 🗑️ 削除したファイル

### 回路ファイル（3件）
- ❌ `circuits/sample_breathing.circom` - breathing_verifierの簡易版（重複）
- ❌ `circuits/cosine_similarity.circom` - 未完成・未使用
- ❌ `circuits/cosine_similarity_test.circom` - 制約エラーで動作しない

### ビルドファイル
- `build/sample_breathing.*`
- `build/cosine_similarity_test.*`

### 鍵ファイル
- `keys/sample_breathing.*`
- `keys/cosine_similarity_test.*`

### スクリプトファイル（4件）
- `scripts/compile_cosine_similarity.js`
- `scripts/setup_cosine_similarity.js`
- `scripts/prove_cosine_similarity.js`
- `scripts/verify_cosine_similarity.js`

### テストファイル
- `test/cosine_similarity.test.js`

### ドキュメント・デバッグファイル
- `COSINE_SIMILARITY_GUIDE.md`
- `scripts/debug_norm.js`

## ✅ 保持したファイル

### 回路ファイル（2件）

#### 1. breathing_verifier.circom
- **目的**: 呼吸数の範囲検証 + 信頼度スコア検証
- **状態**: ✅ テスト完備、動作確認済み
- **用途**: 呼吸数の妥当性検証

#### 2. csi_subcarrier_selector.circom ⭐
- **目的**: CSIサブキャリア選択（コサイン類似度計算）
- **状態**: ✅ 証明生成・検証成功
- **用途**: メインの実用回路

### 関連ファイル

**ビルドファイル**:
- `build/breathing_verifier.r1cs` (6.0K)
- `build/csi_subcarrier_selector.r1cs` (73K)

**鍵ファイル**:
- `keys/breathing_verifier.zkey` (21K)
- `keys/csi_subcarrier_selector.zkey` (238K)

**テストファイル**:
- `test/circuit.test.js` - breathing_verifier のテスト

**スクリプトファイル**:
- `scripts/compile_csi_selector.js`
- `scripts/setup_csi_selector.js`
- `scripts/prove_csi_selector.js`
- `scripts/verify_csi_selector.js`

**ドキュメント**:
- `README.md` - プロジェクト概要
- `QUICK_START.md` - クイックスタートガイド
- `CSI_SELECTOR_ZKP_GUIDE.md` - 詳細ガイド

## 📊 整理前後の比較

| 項目 | 整理前 | 整理後 | 削減 |
|------|--------|--------|------|
| 回路ファイル | 5 | 2 | -3 |
| ビルドファイル | 4 | 2 | -2 |
| 鍵ファイル | 4 | 2 | -2 |
| テストファイル | 2 | 1 | -1 |
| スクリプト | ~15 | ~11 | -4 |

## 🎯 整理の効果

1. **明確な目的**: 2つの実用回路のみに集中
2. **メンテナンス性向上**: 動作する回路のみを保持
3. **混乱の排除**: 失敗した実装や重複を削除
4. **ドキュメント整備**: 残った回路の使い方を明確化

## 🚀 次のステップ

1. `csi_subcarrier_selector.circom` をバックエンドAPIと統合
2. ZKP証明生成サービスの実装
3. IPFS連携の実装

---
整理実行日: 2025-11-11
