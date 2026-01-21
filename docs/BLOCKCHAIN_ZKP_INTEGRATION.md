# ブロックチェーンZKP証明統合ガイド

## 概要

このドキュメントは、ZKP（Zero-Knowledge Proof）証明のみをブロックチェーンに記録するシステムの設定と使用方法を説明します。

## アーキテクチャ

### システムコンポーネント

```
┌─────────────────────────────────────────────────────────────┐
│                    CSI分析システム                           │
│  ┌──────────────┐    ┌──────────────┐                       │
│  │  ZKPサービス  │───▶│ CSI解析結果   │                       │
│  └──────────────┘    └──────────────┘                       │
│         │                    │                               │
│         │                    │ ZKP証明のみ抽出               │
│         ▼                    ▼                               │
│  ┌─────────────────────────────────────┐                    │
│  │  ブロックチェーンサービス             │                    │
│  └─────────────────────────────────────┘                    │
│         │                                                    │
└─────────┼────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│              Ethereum ブロックチェーン                        │
│  ┌─────────────────────────────────────┐                    │
│  │  ZKProofRegistry スマートコントラクト│                    │
│  │  - 証明データ（proof）                │                    │
│  │  - 公開信号（publicSignals）          │                    │
│  │  - メタデータ（デバイスID、タイプ等）  │                    │
│  └─────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

### データフロー

### 自動記録モード（デフォルト）

1. **CSIデータアップロード** → バックエンドが受信
2. **CSI解析 + ZKP証明生成** → コサイン類似度計算
3. **自動ブロックチェーン記録** → ZKP証明のみを自動的に記録
4. **証明検証** → いつでもブロックチェーンから取得・検証可能

## セットアップ

### 1. 前提条件

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+（ZKP回路コンパイル用）

### 2. Ganache（ローカルEthereumノード）起動

開発環境では、Ganacheをローカルで起動します。

```bash
# docker-compose.ymlにGanacheサービスが含まれている場合
docker-compose up ganache -d

# または手動で起動
docker run -d -p 8545:8545 trufflesuite/ganache-cli:latest
```

### 3. スマートコントラクトのデプロイ

ZKProofRegistryコントラクトをデプロイします。

```bash
# 必要なPythonパッケージをインストール
cd backend
pip install web3 py-solc-x python-dotenv

# コントラクトをデプロイ
python contracts/deploy_zkproof_contract.py
```

デプロイが成功すると、以下の情報が表示されます：

```
✅ デプロイ完了!
   コントラクトアドレス: 0x1234...
   ブロック番号: 1
   ガス使用量: 3500000
```

コントラクトアドレスは `.env` ファイルに自動的に追記されます。

**Docker起動時の自動デプロイ**: `backend/entrypoint.sh` でアーティファクトが見つからない場合、
上記のデプロイ手順を自動実行して `backend/contracts/build/ZKProofRegistry.json` を生成します。

### 4. 環境変数の設定

`backend/.env` に以下の変数を追加・確認します：

```env
# Ethereumノード接続URL
# Docker環境では ganache サービスに自動接続（http://ganache:8545）
ETHEREUM_RPC_URL=http://localhost:8545

# ZKProofRegistryコントラクトアドレス（デプロイ時に自動設定）
ZKPROOF_CONTRACT_ADDRESS=0x1234...

# トランザクション署名用の秘密鍵（オプション、本番環境では必須）
# 開発環境では省略可（Ganacheの最初のアカウントを使用）
BLOCKCHAIN_PRIVATE_KEY=
```

**重要**: CSIデータのアップロード時に自動的にZKP証明がブロックチェーンに記録されます。

### 5. バックエンド再起動

環境変数を読み込むため、バックエンドを再起動します。

```bash
docker-compose restart backend

# または手動起動の場合
cd backend
python -m uvicorn app.main:app --reload
```

## 使用方法

### 自動ブロックチェーン記録（推奨）

CSIデータをアップロードするだけで自動的にZKP証明がブロックチェーンに記録されます。

#### 動作フロー

1. CSIデータをアップロード（`POST /api/csi-data/upload`）
2. バックグラウンドで自動的にPCAP解析とZKP証明生成
3. **ZKP証明が自動的にブロックチェーンに記録される** ✨
4. レスポンスのprocessed_dataに `blockchain_proof_id` が含まれる

#### CSIデータのアップロード例

```bash
curl -X POST http://localhost:8000/api/csi-data/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@csi_data.pcap" \
  -F "device_id=device_001"
```

バックグラウンド処理が完了すると、ログに以下のメッセージが表示されます：

```
ZKP proof automatically recorded on blockchain: CSI data <ID>, proof ID 0xabc123...
```

CSIデータ取得時、`processed_data.blockchain_proof_id` でブロックチェーン証明IDを確認できます。

### APIエンドポイント

すべてのエンドポイントは `/api/blockchain` プレフィックスを持ちます。

#### 1. ブロックチェーン接続状態の確認

```bash
curl http://localhost:8000/api/blockchain/status
```

**レスポンス例:**
```json
{
  "connected": true,
  "rpc_url": "http://localhost:8545",
  "contract_address": "0x1234...",
  "chain_id": 1337,
  "current_block": 10,
  "contract_info": {
    "owner": "0xabc...",
    "total_proof_count": 5,
    "current_block": 10
  }
}
```

#### 2. 証明IDから証明を取得

```bash
curl http://localhost:8000/api/blockchain/proof/0xabcd1234...
```

**レスポンス例:**
```json
{
  "device_id": "test_device_001",
  "proof_data": {
    "pi_a": ["123", "456", "1"],
    "pi_b": [["789", "012"], ["345", "678"], ["1", "0"]],
    "pi_c": ["901", "234", "1"],
    "protocol": "groth16"
  },
  "public_signals": ["100", "200", "300"],
  "proof_type": "full_similarity",
  "data_hash": "0x5678...",
  "timestamp": 1704067200,
  "recorder": "0xabc...",
  "verified": false,
  "exists": true
}
```

#### 3. デバイスの証明一覧を取得

```bash
curl http://localhost:8000/api/blockchain/device/test_device_001/proofs
```

**レスポンス例:**
```json
{
  "device_id": "test_device_001",
  "proof_count": 3,
  "proof_ids": [
    "0xabcd1234...",
    "0xef567890...",
    "0x12345678..."
  ]
}
```

#### 4. デバイスの最新証明を取得

```bash
curl http://localhost:8000/api/blockchain/device/test_device_001/latest-proof
```

#### 5. 証明を検証済みとしてマーク

```bash
curl -X POST http://localhost:8000/api/blockchain/verify-proof-on-chain \
  -H "Content-Type: application/json" \
  -d '{
    "proof_id": "0xabcd1234...",
    "is_valid": true
  }'
```

### コマンドラインツール

#### ブロックチェーン状態の確認

```bash
python backend/contracts/check_zkproof_blockchain.py

# 最近の5件の証明を表示
python backend/contracts/check_zkproof_blockchain.py --recent 5

# 特定の証明IDを確認
python backend/contracts/check_zkproof_blockchain.py --proof-id 0xabcd1234...

# デバイスの証明を確認
python backend/contracts/check_zkproof_blockchain.py --device test_device_001

# 証明タイプ別統計を表示
python backend/contracts/check_zkproof_blockchain.py --stats
```

## スマートコントラクト詳細

### ZKProofRegistry.sol

ZKP証明を記録・管理するスマートコントラクト。

#### 主要機能

- **recordZKProof**: ZKP証明を記録
- **getZKProofById**: 証明IDから証明を取得
- **getDeviceProofIds**: デバイスの証明ID一覧を取得
- **markProofAsVerified**: 証明を検証済みとしてマーク
- **batchRecordZKProofs**: 複数の証明を一括記録

#### アクセス制御

- **authorizedRecorders**: 証明を記録できるアドレスのホワイトリスト
- **authorizedVerifiers**: 証明を検証できるアドレスのホワイトリスト
- **owner**: コントラクトオーナー（管理者）

#### イベント

- **ZKProofRecorded**: 証明が記録された際に発行
- **ZKProofVerified**: 証明が検証された際に発行

## セキュリティ考慮事項

### プライバシー保護

- ✅ **元データは保存しない**: ブロックチェーンには証明のみを記録
- ✅ **ZKP証明**: 元データを明かさずに計算の正当性を証明
- ✅ **公開信号のみ**: 必要最小限の情報のみ公開

### アクセス制御

- ✅ **ホワイトリスト**: 認可されたアドレスのみが証明を記録可能
- ✅ **検証者制限**: 証明の検証マークは認可された検証者のみ
- ✅ **オーナー権限**: コントラクトの管理者権限

### ガスコスト最適化

- 証明データはJSON文字列として保存（ガスコスト大）
- バッチ処理で複数証明を効率的に記録

## トラブルシューティング

### ブロックチェーンに接続できない

```bash
# Ganacheが起動しているか確認
docker ps | grep ganache

# ポート8545がリッスンしているか確認
lsof -i :8545

# Ganacheを再起動
docker-compose restart ganache
```

### コントラクトアドレスが見つからない

```bash
# コントラクトを再デプロイ
python backend/contracts/deploy_zkproof_contract.py

# .envファイルを確認
cat backend/.env | grep ZKPROOF_CONTRACT_ADDRESS
```

### トランザクションが失敗する

- Ganacheアカウントの残高を確認
- ガス価格が適切か確認
- コントラクトのアクセス制御を確認（authorizedRecorders）

## 本番環境デプロイ

### 1. Ethereumメインネット/テストネットへのデプロイ

```bash
# Infura/Alchemy等のノードプロバイダーURLを設定
export ETHEREUM_RPC_URL=https://mainnet.infura.io/v3/YOUR_PROJECT_ID

# デプロイアカウントの秘密鍵を設定（絶対に公開しない）
export BLOCKCHAIN_PRIVATE_KEY=0x...

# コントラクトをデプロイ
python backend/contracts/deploy_zkproof_contract.py
```

### 2. 環境変数の設定（本番）

```env
ETHEREUM_RPC_URL=https://mainnet.infura.io/v3/YOUR_PROJECT_ID
ZKPROOF_CONTRACT_ADDRESS=0x...
BLOCKCHAIN_PRIVATE_KEY=0x...  # 絶対に.gitignoreに含める
```

### 3. セキュリティチェックリスト

- [ ] 秘密鍵は環境変数から読み込み、コードに含めない
- [ ] コントラクトのアクセス制御を適切に設定
- [ ] ガス価格を監視し、コストを最適化
- [ ] Etherscanでコントラクトを検証（透明性向上）
- [ ] バックエンドサーバーのファイアウォール設定

## まとめ

このシステムでは、ZKP証明のみをブロックチェーンに記録することで、以下を実現しています：

1. **プライバシー保護**: 元のCSIデータは公開しない
2. **透明性**: 証明は誰でも検証可能
3. **改ざん防止**: ブロックチェーンの不変性により証明の信頼性を保証
4. **監査可能性**: すべての証明記録は追跡可能

詳細な技術情報は、各ソースコードのコメントを参照してください。
