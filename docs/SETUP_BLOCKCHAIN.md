# ブロックチェーン統合セットアップガイド

このガイドでは、CSI WebプラットフォームにIPFS + ブロックチェーン統合機能をセットアップして動作確認する手順を説明します。

## 📋 前提条件

- Docker & Docker Compose がインストール済み
- Python 3.11以上
- Node.js 18以上（フロントエンド開発の場合）

---

## 🚀 セットアップ手順

### ステップ1: システム起動

#### 1.1 全サービスを起動

```bash
# プロジェクトルートディレクトリで実行
docker-compose up -d
```

起動されるサービス:
- ✅ PostgreSQL (ポート: 5432)
- ✅ Redis (ポート: 6379)
- ✅ IPFS (ポート: 5001, 8080)
- ✅ **Ganache** (ポート: 8545) - ローカルブロックチェーン
- ✅ Backend (ポート: 8000)
- ✅ Frontend (ポート: 3000)

#### 1.2 サービス起動確認

```bash
# 各サービスの状態を確認
docker-compose ps

# Ganacheの起動を確認
docker-compose logs ganache

# バックエンドの起動を確認
docker-compose logs backend
```

### ステップ2: データベースマイグレーション実行

#### 2.1 バックエンドコンテナに入る

```bash
docker-compose exec backend bash
```

#### 2.2 マイグレーションを実行

```bash
# Alembicマイグレーションを実行
cd /app
alembic upgrade head
```

**期待される出力:**
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> bc123456789a, add blockchain fields to csi_data
```

#### 2.3 データベース確認

```bash
# PostgreSQLに接続してテーブル確認
docker-compose exec postgres psql -U csi_user -d csi_system

# csi_dataテーブルの構造を確認
\d csi_data

# 新しいフィールドが追加されていることを確認:
# - blockchain_tx_hash
# - blockchain_status
# - blockchain_recorded_at

# 終了
\q
```

### ステップ3: スマートコントラクトのデプロイ

#### 3.1 必要なPythonパッケージのインストール

```bash
# バックエンドコンテナ内で実行（まだ入っていない場合）
docker-compose exec backend bash

# 依存関係をインストール
pip install web3 eth-account py-solc-x python-dotenv
```

#### 3.2 コントラクトをデプロイ

```bash
# デプロイスクリプトを実行
python backend/contracts/deploy_contract.py
```

**期待される出力:**
```
============================================================
CSI Data Registry スマートコントラクト デプロイツール
============================================================

🔗 Ethereumノードに接続中: http://ganache:8545
✅ 接続成功
   チェーンID: 1337
   ブロック番号: 0

📝 Solidityコンパイラをインストール中...
📄 コントラクトを読み込み中: backend/contracts/CSIDataRegistry.sol
🔨 コントラクトをコンパイル中...
✅ コンパイル完了

🚀 コントラクトをデプロイ中...
   アカウント: 0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1
   残高: 100.0 ETH
   トランザクションハッシュ: 0x...
   トランザクション確認待機中...

✅ デプロイ完了!
   コントラクトアドレス: 0x...
   ブロック番号: 1
   ガス使用量: 2547123

💾 コントラクト情報を保存しました: backend/contracts/build/CSIDataRegistry.json
✅ backend/.env を更新しました

============================================================
🎉 デプロイが正常に完了しました!
============================================================
```

#### 3.3 バックエンドサービスを再起動

コントラクトアドレスを環境変数に反映させるため、バックエンドを再起動します。

```bash
# バックエンドコンテナから抜ける
exit

# バックエンドを再起動
docker-compose restart backend

# 再起動を確認
docker-compose logs -f backend
```

### ステップ4: 動作確認

#### 4.1 ヘルスチェック

```bash
# バックエンドAPIのヘルスチェック
curl http://localhost:8000/health

# 期待されるレスポンス:
# {"status":"healthy","timestamp":"..."}
```

#### 4.2 ブロックチェーン接続確認

バックエンドログでブロックチェーン接続を確認:

```bash
docker-compose logs backend | grep -i blockchain
```

**期待されるログ:**
```
INFO - Blockchain service initialized successfully
INFO - Connected to Ethereum network - Chain ID: 1337, Block: 1
INFO - Contract loaded at: 0x...
```

#### 4.3 CSIデータアップロードテスト

##### 4.3.1 ユーザー登録・ログイン

```bash
# 管理者アカウントでログイン
curl -X POST http://localhost:8000/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

レスポンスからアクセストークンをコピーします。

##### 4.3.2 テストデータのアップロード

```bash
# サンプルデータファイルを作成
echo "CSI Test Data" > /tmp/test_csi_data.txt

# CSIデータをアップロード（TOKENを置き換えてください）
curl -X POST http://localhost:8000/api/v2/csi-data/upload-test \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -F "device_id=test_device_001" \
  -F "file=@/tmp/test_csi_data.txt"
```

**期待されるレスポンス:**
```json
{
  "id": "...",
  "device_id": "test_device_001",
  "file_path": "...",
  "file_size": 14,
  "ipfs_hash": "QmXXXXXXXX...",
  "blockchain_tx_hash": "0xXXXXXXXX...",
  "blockchain_status": "pending",
  "status": "received",
  "created_at": "2025-10-14T..."
}
```

#### 4.4 ブロックチェーン記録の確認

##### 4.4.1 バックエンドログを確認

```bash
docker-compose logs backend | grep -i "blockchain\|ipfs"
```

**期待されるログ:**
```
INFO - CSI data package uploaded to IPFS: QmXXXXXXXX...
INFO - CSI data CID recorded on blockchain: 0xXXXXXXXX...
```

##### 4.4.2 Ganacheでトランザクションを確認

```bash
# Ganacheコンテナのログを確認
docker-compose logs ganache | tail -20
```

トランザクションが記録されていることを確認できます。

---

## 🧪 高度な動作確認

### Python CLIでブロックチェーン情報を取得

`backend/contracts/`ディレクトリに簡単なテストスクリプトを作成:

```python
# backend/contracts/test_contract.py
from web3 import Web3
import json

# Web3に接続
w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))
print(f"接続状態: {w3.is_connected()}")
print(f"ブロック番号: {w3.eth.block_number}")

# コントラクト情報を読み込み
with open('backend/contracts/build/CSIDataRegistry.json', 'r') as f:
    contract_data = json.load(f)

contract = w3.eth.contract(
    address=contract_data['address'],
    abi=contract_data['abi']
)

# コントラクト情報を取得
info = contract.functions.getContractInfo().call()
print(f"\nコントラクト情報:")
print(f"  オーナー: {info[0]}")
print(f"  総記録件数: {info[1]}")
print(f"  現在のブロック: {info[2]}")

# 最新の記録を確認（記録がある場合）
if info[1] > 0:
    print(f"\n📝 記録されたデータがあります！")
```

実行:
```bash
docker-compose exec backend python backend/contracts/test_contract.py
```

---

## 🔍 トラブルシューティング

### 問題1: Ganacheに接続できない

**症状:**
```
❌ エラー: Ethereumノードに接続できません
```

**解決方法:**
```bash
# Ganacheが起動しているか確認
docker-compose ps ganache

# 起動していない場合
docker-compose up -d ganache

# ログを確認
docker-compose logs ganache
```

### 問題2: コントラクトデプロイに失敗

**症状:**
```
❌ エラー: Contract logic error
```

**解決方法:**
```bash
# Ganacheを再起動してブロックチェーンをリセット
docker-compose restart ganache

# 再度デプロイを試行
docker-compose exec backend python backend/contracts/deploy_contract.py
```

### 問題3: マイグレーションエラー

**症状:**
```
ERROR [alembic.runtime.migration] Can't locate revision identified by 'bc123456789a'
```

**解決方法:**
```bash
# Alembicの状態を確認
docker-compose exec backend alembic current

# マイグレーション履歴を確認
docker-compose exec backend alembic history

# 必要に応じてデータベースをリセット
docker-compose down -v
docker-compose up -d
```

### 問題4: IPFS接続エラー

**症状:**
```
WARNING - IPFS upload failed, continuing without IPFS
```

**解決方法:**
```bash
# IPFSコンテナが起動しているか確認
docker-compose ps ipfs

# IPFSコンテナを再起動
docker-compose restart ipfs

# IPFS APIの疎通確認
curl -X POST http://localhost:5001/api/v0/version
```

---

## 📊 システム構成図

```
┌─────────────────┐
│   Frontend      │ :3000
│   (Next.js)     │
└────────┬────────┘
         │
         ↓ HTTP
┌─────────────────┐
│   Backend       │ :8000
│   (FastAPI)     │
└────────┬────────┘
         │
    ┌────┼────┬─────────┬──────────┐
    ↓    ↓    ↓         ↓          ↓
┌────┐ ┌────┐ ┌────┐ ┌────────┐ ┌────────┐
│ PG │ │Redis│ │IPFS│ │Ganache │ │Uploads │
│5432│ │6379│ │5001│ │  8545  │ │ Volume │
└────┘ └────┘ └────┘ └────────┘ └────────┘
                         │
                         ↓
            ┌─────────────────────┐
            │ Smart Contract      │
            │ CSIDataRegistry     │
            │ (記録されたCID)      │
            └─────────────────────┘
```

---

## 📈 データフロー

```
1. CSIデータアップロード
   ↓
2. ローカルストレージ保存
   ↓
3. IPFS アップロード
   → CID取得: QmXXXXXX...
   ↓
4. PostgreSQL 保存
   → ipfs_hash: QmXXXXXX...
   ↓
5. ブロックチェーン記録
   → トランザクション送信
   ↓
6. トランザクション確認
   → blockchain_tx_hash: 0xXXXXXX...
   ↓
7. データベース更新
   → blockchain_status: "confirmed"
```

---

## ✅ セットアップ完了チェックリスト

- [ ] Docker Composeで全サービスが起動
- [ ] PostgreSQLマイグレーション完了
- [ ] Ganacheが起動中（ポート8545）
- [ ] スマートコントラクトがデプロイ済み
- [ ] バックエンドがコントラクトに接続
- [ ] IPFS接続確認
- [ ] CSIデータアップロードテスト成功
- [ ] ブロックチェーン記録確認

すべてにチェックが入れば、ブロックチェーン統合機能のセットアップは完了です！

---

## 🎉 次のステップ

1. **フロントエンド開発**: ブロックチェーン状態の表示UI実装
2. **APIエンドポイント追加**: CID検索、トランザクション確認API
3. **本番環境構築**: Testnet (Goerli/Sepolia) への移行
4. **監視・ロギング**: ブロックチェーントランザクションの監視

---

**最終更新**: 2025-10-14
**バージョン**: 2.0.0
**ステータス**: ✅ 動作確認済み（ローカル環境）
**作成者**: CSI Web Platform Development Team

---

## ✅ 動作確認済み情報

### テスト実施日時
- 2025-10-14 実施
- 全機能正常動作確認完了

### 確認済み項目
- ✅ Docker Compose全サービス起動（backend, frontend, postgres, redis, ipfs, ganache）
- ✅ Ganache起動（Network ID: 1337、ブロック番号: 1）
- ✅ スマートコントラクトデプロイ（アドレス: 0x5FbDB2315678afecb367f032d93F642f64180aa3）
- ✅ データベースマイグレーション（blockchain_tx_hash, blockchain_status, blockchain_recorded_at追加）
- ✅ バックエンドAPI（認証、デバイス管理、CSIデータ管理）
- ✅ フロントエンド（http://localhost:3000、コンパイル正常）
- ✅ IPFS接続（API: 5001、Gateway: 8080）

### 既知の制限事項
- デバイス専用の認証トークンが必要（CSIデータアップロードAPI）
- マイグレーションファイルの自動認識は手動対応が必要な場合あり
