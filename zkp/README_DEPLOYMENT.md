# ZKP本番デプロイガイド

## 🎯 概要

本番環境では**ZKP回路のみ**でコサイン類似度計算を実行します。
JavaScript/Python実装は開発環境専用です。

---

## 📦 本番デプロイに必要なファイル

### ✅ 必須ファイル

```
zkp/
├── circuits/
│   └── csi_subcarrier_selector.circom  ✅ ZKP回路ソースコード
├── build/
│   └── csi_subcarrier_selector_js/     ✅ コンパイル済みWASM
│       ├── csi_subcarrier_selector.wasm
│       ├── generate_witness.js
│       └── witness_calculator.js
└── keys/
    ├── csi_subcarrier_selector_final.zkey           ✅ 証明キー
    └── csi_subcarrier_selector_verification_key.json ✅ 検証キー
```

### ❌ デプロイ除外ファイル（開発専用）

```
zkp/
├── scripts/                                    ❌ 開発用スクリプト
│   ├── calculate_all_subcarrier_similarity.js
│   ├── compare_similarity_accuracy.py
│   └── prove_from_all_subcarriers.js
├── data/                                       ❌ 開発用データ
│   ├── similarity_results/
│   ├── similarity_comparison/
│   └── subcarrier_selection/
└── sample/                                     ❌ サンプルデータ
```

---

## 🚀 デプロイ手順

### 1. ローカル環境でのビルド

```bash
cd zkp

# 依存関係インストール
npm install

# 回路コンパイル
npm run compile:csi_selector

# Trusted Setup
npm run setup:csi_selector

# 動作確認（開発環境のみ）
npm run test:csi_selector
```

### 2. ビルド成果物の確認

```bash
# 必須ファイルの存在確認
ls -la build/csi_subcarrier_selector_js/csi_subcarrier_selector.wasm
ls -la keys/csi_subcarrier_selector_final.zkey
ls -la keys/csi_subcarrier_selector_verification_key.json
```

### 3. 本番環境へのデプロイ

**方法A: Dockerイメージに含める**

```dockerfile
# Dockerfile.production
FROM node:18-alpine

WORKDIR /app

# ZKP必須ファイルのみコピー
COPY zkp/circuits zkp/circuits
COPY zkp/build/csi_subcarrier_selector_js zkp/build/csi_subcarrier_selector_js
COPY zkp/keys zkp/keys

# 開発用ファイルは除外（COPYしない）
# zkp/scripts/
# zkp/data/
# zkp/sample/
```

**方法B: rsyncでデプロイ**

```bash
# .deployignore を使用して除外ファイルを指定
rsync -av --exclude-from=.deployignore . user@production:/app/
```

---

## 🔒 セキュリティ

### キーファイルの管理

```bash
# 本番環境でのキーファイルは読み取り専用
chmod 444 zkp/keys/csi_subcarrier_selector_final.zkey
chmod 444 zkp/keys/csi_subcarrier_selector_verification_key.json
```

### 環境変数

```bash
# backend/.env.production
ZKP_ENABLED=true
ZKP_DEVELOPMENT_MODE=false
ALLOW_JS_SIMILARITY=false
ALLOW_PYTHON_SIMILARITY=false
```

---

## ✅ デプロイ後の検証

### 1. ZKPサービスの動作確認

```bash
# バックエンドログ確認
docker-compose logs -f backend | grep "ZKP"

# 期待されるログ出力:
# INFO: ZKP Service initialized with circuit: csi_subcarrier_selector
# INFO: Cosine similarity ZKP generated: bestIndex=0, similarity=0.9999
```

### 2. APIエンドポイントテスト

```bash
# ZKP証明生成API（要認証）
curl -X POST http://localhost:8000/api/v2/zkp/generate-proof \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reference_vector": [3, 4, 0, 0],
    "candidate_vectors": [[3, 4, 0, 0], [4, 3, 0, 0]],
    "scale": 10000
  }'
```

---

## 📊 パフォーマンスモニタリング

### 目標値

| 指標 | 目標値 |
|-----|-------|
| ZKP証明生成時間 | < 2秒 |
| ZKP検証時間 | < 100ms |
| メモリ使用量 | < 512MB |
| 並列処理数 | 10証明/秒 |

### モニタリング方法

```bash
# Prometheusメトリクス（将来実装）
# /metrics エンドポイントで以下を公開:
# - zkp_proof_generation_duration_seconds
# - zkp_verification_duration_seconds
# - zkp_proof_generation_total
# - zkp_proof_verification_failures_total
```

---

## 🔄 アップデート手順

### 回路の更新時

```bash
# 1. 新しい回路をコンパイル
npm run compile:csi_selector

# 2. 新しいTrusted Setupを実行
npm run setup:csi_selector

# 3. ローカルでテスト
npm run test:csi_selector

# 4. 本番環境にデプロイ
# - build/ 更新
# - keys/ 更新
# - バックエンド再起動
```

---

## ⚠️ トラブルシューティング

### エラー: "WASM file not found"

```bash
# 原因: ZKP回路がコンパイルされていない
# 解決策:
cd zkp
npm run compile:csi_selector
```

### エラー: "zkey file not found"

```bash
# 原因: Trusted Setupが実行されていない
# 解決策:
cd zkp
npm run setup:csi_selector
```

### エラー: "Witness generation failed"

```bash
# 原因: 入力データの形式が不正
# 解決策:
# - 参照ベクトル・候補ベクトルが4次元であることを確認
# - 候補ベクトルが最大2個であることを確認
# - 全ての値が整数であることを確認
```

---

## 📝 チェックリスト

### デプロイ前

- [ ] ZKP回路のコンパイル完了
- [ ] Trusted Setup完了
- [ ] ローカル環境でのテスト完了
- [ ] 環境変数が本番設定
- [ ] 開発用スクリプトが除外されている
- [ ] キーファイルのパーミッション設定

### デプロイ後

- [ ] ZKPサービスの初期化ログ確認
- [ ] API証明生成テスト成功
- [ ] API検証テスト成功
- [ ] パフォーマンス目標達成
- [ ] エラーログに異常なし

---

## 📚 関連ドキュメント

- **アーキテクチャ設計**: `docs/ZKP_DEPLOYMENT_ARCHITECTURE.md`
- **回路仕様**: `zkp/circuits/README_CSI_Selector.md`
- **API仕様**: `backend/app/api/endpoints/zkp.py`
- **環境設定**: `backend/.env.production.example`
