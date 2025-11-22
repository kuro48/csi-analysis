# ZKP (Zero-Knowledge Proof) System

Wi-Fi CSI呼吸監視システムのゼロ知識証明実装

---

## 🎯 概要

**本番環境**: ZKP回路のみでコサイン類似度計算（プライバシー保護）
**開発環境**: 開発・テスト用の追加機能も利用可能

---

## 📁 プロジェクト構成

```
zkp/
├── circuits/
│   ├── csi_subcarrier_selector.circom  # CSIサブキャリア選択回路
│   └── README_CSI_Selector.md          # 回路仕様ドキュメント
├── scripts/
│   ├── compile_csi_selector.js         # 回路コンパイル
│   ├── setup_csi_selector.js           # Trusted Setup
│   └── verify_csi_fft.js               # ZKP証明検証
├── build/                               # コンパイル出力（WASM）
├── keys/                                # 証明鍵・検証鍵
├── proofs/                              # 生成された証明
└── README_DEPLOYMENT.md                 # 本番デプロイガイド ⭐
```

---

## 🚀 セットアップ

### 1. 依存関係インストール

```bash
npm install
```

### 2. ZKP回路のコンパイル

```bash
# CSIサブキャリア選択回路をコンパイル
npm run compile:csi_selector
```

### 3. Trusted Setup

```bash
# 証明キー・検証キーを生成（初回のみ、約5分）
npm run setup:csi_selector
```

### 4. 動作確認

```bash
# 証明検証テスト
npm run test:csi_selector
```

---

## 🎯 主要機能

### CSIサブキャリア選択ZKP回路

- **コサイン類似度計算**: 最適なサブキャリアペアを選択
- **Groth16プロトコル**: 効率的なZKP証明
- **整数演算**: Pythagorean tripleパターンで完全一致保証
- **プライバシー保護**: 生データを秘匿したまま証明生成

### 技術仕様

- **ベクトル次元**: 4次元
- **候補数**: 最大2個
- **固定小数点スケール**: 10000（0.0〜1.0 → 0〜10000）
- **検証式**: `similarity × normA × normB = dotProduct × SCALE`

---

## 🔐 本番環境での使用

### バックエンドAPIからの利用

本番環境では、バックエンドの`ZKPService`を経由してZKP証明を生成・検証します。

```python
from app.services.zkp_service import ZKPService

zkp_service = ZKPService()

# ZKP証明生成
result = await zkp_service.generate_cosine_similarity_proof(
    reference_vector=[3, 4, 0, 0],
    candidate_vectors=[[3, 4, 0, 0], [4, 3, 0, 0]],
    scale=10000
)

# ZKP証明検証
is_valid = await zkp_service.verify_cosine_similarity_proof(
    proof=result["proof"],
    public_signals=result["publicSignals"]
)
```

### 環境設定

**本番環境** (`.env.production`):
```bash
ZKP_ENABLED=true
ZKP_DEVELOPMENT_MODE=false
```

**開発環境** (`.env.development`):
```bash
ZKP_ENABLED=true
ZKP_DEVELOPMENT_MODE=true
```

---

## 📚 ドキュメント

- **デプロイガイド**: `README_DEPLOYMENT.md` - 本番デプロイ手順
- **回路仕様**: `circuits/README_CSI_Selector.md` - 回路の詳細説明
- **アーキテクチャ設計**: `../docs/ZKP_DEPLOYMENT_ARCHITECTURE.md` - システム全体のアーキテクチャ

---

## ⚠️ 重要な制約

### Pythagorean Tripleパターンが必須

ZKP回路の検証式は**完全一致**が必要です。

**✅ 使用可能なパターン**:
```javascript
[3, 4, 0, 0]   // norm = 5
[5, 12, 0, 0]  // norm = 13
[8, 15, 0, 0]  // norm = 17
```

**❌ 使用不可**:
```javascript
[1, 2, 3, 4]  // norm = 5.477... (非整数 → 丸め誤差発生)
```

---

## 🔧 開発環境のみ

開発環境では、追加の開発用機能が利用可能です：

- JavaScript直接計算（Witness生成・精度比較）
- Python高精度リファレンス実装
- 開発用スクリプト・データ

**注意**: これらの機能は本番環境では無効化され、デプロイパッケージには含まれません。

---

## 🚢 本番デプロイ

詳細は `README_DEPLOYMENT.md` を参照してください。

### デプロイチェックリスト

- [ ] ZKP回路のコンパイル完了
- [ ] Trusted Setup完了
- [ ] 環境変数が本番設定（`ZKP_DEVELOPMENT_MODE=false`）
- [ ] ビルド成果物の検証
- [ ] ZKP証明の生成・検証テスト完了

---

## 📊 パフォーマンス

| 指標 | 目標値 |
|-----|-------|
| ZKP証明生成時間 | < 2秒 |
| ZKP検証時間 | < 100ms |
| メモリ使用量 | < 512MB |

---

## 🛠️ トラブルシューティング

### エラー: "WASM file not found"

```bash
# 解決策: 回路をコンパイル
npm run compile:csi_selector
```

### エラー: "zkey file not found"

```bash
# 解決策: Trusted Setupを実行
npm run setup:csi_selector
```

### エラー: "Witness generation failed"

```bash
# 原因: 入力データの形式が不正
# 確認事項:
# - ベクトルが4次元であること
# - 候補ベクトルが最大2個であること
# - 全ての値が整数であること
```

---

## 📝 ライセンス

このプロジェクトの一部として提供されます。
