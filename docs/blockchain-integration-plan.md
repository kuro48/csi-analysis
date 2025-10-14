# IPFS CID + ブロックチェーン統合実装計画

## 📋 概要

このドキュメントは、CSI Webプラットフォームにブロックチェーン統合を実装する計画を詳述しています。

### 目的
- IPFSに保存したCSIデータのCID（Content Identifier）をブロックチェーンに記録
- ブロックチェーン上のCIDを元にCSIデータへの検証可能なアクセスを提供
- データの改ざん防止と透明性を確保

### アーキテクチャ概要
```
エッジデバイス
    ↓
バックエンドAPI（FastAPI）
    ↓
┌─────────────┬──────────────┬──────────────┐
│ローカル保存  │ IPFS保存     │ PostgreSQL   │
│             │ → CID取得    │ メタデータ保存│
└─────────────┴──────────────┴──────────────┘
                ↓
         ブロックチェーン記録
         （Ethereum互換）
         - device_id
         - ipfs_cid
         - timestamp
         - metadata_hash
                ↓
         トランザクションハッシュ
         をPostgreSQLに保存
```

---

## 🎯 実装ステップ

### Phase 1: 基盤整備

#### 1.1 スマートコントラクト開発

**ファイル**: `backend/contracts/CSIDataRegistry.sol`

**機能要件**:
- CID記録関数: `recordCSIData(deviceId, ipfsCid, metadataHash)`
- CID取得関数: `getCSIDataByCID(ipfsCid)`
- デバイス別履歴取得: `getDeviceHistory(deviceId, limit)`
- イベントログ: `CSIDataRecorded(deviceId, ipfsCid, timestamp, txHash)`

**主要機能**:
```solidity
// 構造体定義
struct CSIDataRecord {
    string deviceId;
    string ipfsCid;
    string metadataHash;
    uint256 timestamp;
    address recorder;
}

// マッピング
mapping(string => CSIDataRecord) public cidToRecord;
mapping(string => string[]) public deviceToCids;

// CID記録関数
function recordCSIData(
    string memory deviceId,
    string memory ipfsCid,
    string memory metadataHash
) public returns (bool)

// CID取得関数
function getCSIDataByCID(
    string memory ipfsCid
) public view returns (CSIDataRecord memory)
```

#### 1.2 Docker環境整備

**ファイル**: `docker-compose.yml`

**追加内容**:
```yaml
  # Ganache - ローカル開発用Ethereumブロックチェーン
  ganache:
    image: trufflesuite/ganache:latest
    container_name: csi_ganache
    command: >
      --deterministic
      --accounts 10
      --networkId 1337
      --gasLimit 8000000
      --gasPrice 20000000000
      --mnemonic "your test mnemonic here"
    ports:
      - "8545:8545"
    networks:
      - csi_network
    restart: unless-stopped
```

#### 1.3 依存関係追加

**ファイル**: `backend/requirements.txt`

**追加パッケージ**:
```
# ブロックチェーン関連
web3>=6.0.0
eth-account>=0.9.0
eth-typing>=3.0.0
eth-utils>=2.0.0
py-solc-x>=2.0.0  # Solidityコンパイラ
```

---

### Phase 2: バックエンド実装

#### 2.1 データベースモデル拡張

**ファイル**: `backend/app/models/csi_data.py`

**変更内容** (行33付近):
```python
class CSIData(BaseModel):
    """CSIデータテーブル"""
    __tablename__ = "csi_data"

    # 既存フィールド...

    # ブロックチェーン関連フィールド（新規追加）
    blockchain_tx_hash = Column(
        String(66),
        nullable=True,
        index=True,
        comment="ブロックチェーントランザクションハッシュ"
    )
    blockchain_status = Column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        comment="ブロックチェーン記録状態: pending, confirmed, failed"
    )
    blockchain_recorded_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="ブロックチェーン記録完了時刻"
    )
```

#### 2.2 Alembicマイグレーション

**ファイル**: `backend/database/migrations/versions/xxxx_add_blockchain_fields.py`

**生成コマンド**:
```bash
cd backend
alembic revision --autogenerate -m "add_blockchain_fields_to_csi_data"
```

**マイグレーション内容**:
```python
def upgrade():
    op.add_column('csi_data',
        sa.Column('blockchain_tx_hash', sa.String(66), nullable=True)
    )
    op.add_column('csi_data',
        sa.Column('blockchain_status', sa.String(20),
                  server_default='pending', nullable=False)
    )
    op.add_column('csi_data',
        sa.Column('blockchain_recorded_at',
                  sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index('idx_blockchain_tx_hash', 'csi_data', ['blockchain_tx_hash'])
    op.create_index('idx_blockchain_status', 'csi_data', ['blockchain_status'])

def downgrade():
    op.drop_index('idx_blockchain_status', 'csi_data')
    op.drop_index('idx_blockchain_tx_hash', 'csi_data')
    op.drop_column('csi_data', 'blockchain_recorded_at')
    op.drop_column('csi_data', 'blockchain_status')
    op.drop_column('csi_data', 'blockchain_tx_hash')
```

#### 2.3 ブロックチェーンサービス実装

**ファイル**: `backend/app/services/blockchain_service.py`（新規作成）

**主要クラス・メソッド**:
```python
from web3 import Web3
from eth_account import Account
import logging

class BlockchainService:
    """ブロックチェーンサービス"""

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))
        self.contract = self._load_contract()
        self.account = self._load_account()

    async def record_csi_data_cid(
        self,
        device_id: str,
        ipfs_cid: str,
        metadata_hash: str
    ) -> Dict[str, Any]:
        """
        CSIデータのCIDをブロックチェーンに記録

        Returns:
            {
                "tx_hash": "0x...",
                "status": "pending",
                "block_number": None
            }
        """

    async def get_csi_data_by_cid(
        self,
        ipfs_cid: str
    ) -> Optional[Dict[str, Any]]:
        """
        CIDからブロックチェーン上のデータ情報を取得

        Returns:
            {
                "device_id": "device_001",
                "ipfs_cid": "Qm...",
                "metadata_hash": "Qm...",
                "timestamp": 1234567890,
                "recorder": "0x..."
            }
        """

    async def get_transaction_status(
        self,
        tx_hash: str
    ) -> Dict[str, Any]:
        """トランザクション状態を確認"""

    async def verify_cid_exists(
        self,
        ipfs_cid: str
    ) -> bool:
        """CIDがブロックチェーンに記録されているか確認"""

# シングルトンインスタンス
blockchain_service = BlockchainService()
```

#### 2.4 CSIDataService更新

**ファイル**: `backend/app/services/csi_data.py`

**変更箇所**: `upload_csi_data`メソッド（行33-166付近）

**追加内容**:
```python
# 既存のIPFSアップロード処理の後（行90付近）
ipfs_hash = ipfs_result["combined_hash"]
logger.info(f"CSI data package uploaded to IPFS: {ipfs_hash}")

# ブロックチェーン記録処理を追加
blockchain_tx_hash = None
blockchain_status = "pending"

if settings.BLOCKCHAIN_ENABLED:
    try:
        # ブロックチェーンにCIDを記録（非同期バックグラウンド処理）
        metadata_hash = ipfs_result["metadata_hash"]
        blockchain_result = await blockchain_service.record_csi_data_cid(
            device_id=device_id,
            ipfs_cid=ipfs_hash,
            metadata_hash=metadata_hash
        )
        blockchain_tx_hash = blockchain_result["tx_hash"]
        blockchain_status = blockchain_result["status"]
        logger.info(f"CSI data CID recorded on blockchain: {blockchain_tx_hash}")
    except Exception as e:
        logger.error(f"Blockchain recording failed: {e}")
        blockchain_status = "failed"

# データベースレコード作成時にブロックチェーンフィールドを含める（行123付近）
csi_data = CSIData(
    device_id=device.id,
    session_id=upload_info.session_id,
    raw_data=raw_data if raw_data is None else json.dumps(raw_data) if not isinstance(raw_data, str) else raw_data,
    processed_data=processed_data if processed_data is None else json.dumps(processed_data) if not isinstance(processed_data, str) else processed_data,
    file_path=str(file_path),
    file_size=len(file_data),
    status="processed" if processed_data else "received",
    ipfs_hash=ipfs_hash,
    blockchain_tx_hash=blockchain_tx_hash,  # 追加
    blockchain_status=blockchain_status      # 追加
)
```

#### 2.5 スキーマ拡張

**ファイル**: `backend/app/schemas/csi_data.py`

**変更箇所**: `CSIDataResponse`クラス（行27-42付近）

**追加フィールド**:
```python
class CSIDataResponse(BaseModel):
    """CSIデータレスポンススキーマ"""
    id: uuid.UUID
    device_id: str
    session_id: Optional[str] = None
    raw_data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
    processed_data: Optional[Dict[str, Any]] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    ipfs_hash: Optional[str] = None
    status: str

    # ブロックチェーン関連フィールド（新規追加）
    blockchain_tx_hash: Optional[str] = Field(None, description="ブロックチェーントランザクションハッシュ")
    blockchain_status: Optional[str] = Field(None, description="ブロックチェーン記録状態")
    blockchain_recorded_at: Optional[datetime] = Field(None, description="ブロックチェーン記録完了時刻")

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
```

#### 2.6 ブロックチェーンAPIエンドポイント

**ファイル**: `backend/app/api/endpoints/blockchain.py`（新規作成）

**エンドポイント一覧**:
```python
from fastapi import APIRouter, Depends, HTTPException
from app.services.blockchain_service import blockchain_service

router = APIRouter()

@router.get("/csi-data/{cid}")
async def get_csi_data_by_cid(
    cid: str,
    current_user: User = Depends(get_current_user)
):
    """
    CIDからブロックチェーン上のCSIデータ情報を取得

    GET /api/v2/blockchain/csi-data/QmXXXXXX
    """

@router.get("/transaction/{tx_hash}")
async def get_transaction_status(
    tx_hash: str,
    current_user: User = Depends(get_current_user)
):
    """
    トランザクション状態を確認

    GET /api/v2/blockchain/transaction/0xXXXXXX
    """

@router.post("/retry-record/{csi_data_id}")
async def retry_blockchain_record(
    csi_data_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ブロックチェーン記録をリトライ

    POST /api/v2/blockchain/retry-record/{csi_data_id}
    """

@router.get("/verify/{cid}")
async def verify_cid(
    cid: str,
    current_user: User = Depends(get_current_user)
):
    """
    CIDがブロックチェーンに記録されているか検証

    GET /api/v2/blockchain/verify/QmXXXXXX
    """
```

**ルーター登録**: `backend/app/main.py`に追加
```python
from app.api.endpoints import blockchain

app.include_router(
    blockchain.router,
    prefix=f"{settings.API_V2_PREFIX}/blockchain",
    tags=["blockchain"]
)
```

#### 2.7 設定ファイル拡張

**ファイル**: `backend/app/core/config.py`

**変更箇所**: 行78-96付近

**追加設定**:
```python
class Settings:
    # 既存設定...

    # ブロックチェーン設定（拡張）
    BLOCKCHAIN_ENABLED: bool = os.getenv("BLOCKCHAIN_ENABLED", "true").lower() == "true"
    BLOCKCHAIN_NODE_HOST: str = os.getenv("BLOCKCHAIN_NODE_HOST", "ganache")
    BLOCKCHAIN_NODE_PORT: int = int(os.getenv("BLOCKCHAIN_NODE_PORT", "8545"))
    ETHEREUM_RPC_URL: str = os.getenv(
        "ETHEREUM_RPC_URL",
        "http://ganache:8545"  # Docker環境用
    )

    # スマートコントラクト設定
    CONTRACT_ADDRESS: str = os.getenv(
        "CONTRACT_ADDRESS",
        "0x0000000000000000000000000000000000000000"  # デプロイ後に更新
    )
    CONTRACT_ABI_PATH: str = os.getenv(
        "CONTRACT_ABI_PATH",
        "backend/contracts/build/CSIDataRegistry.json"
    )

    # アカウント設定（注意: 本番環境では環境変数から読み込む）
    BLOCKCHAIN_ACCOUNT_ADDRESS: str = os.getenv(
        "BLOCKCHAIN_ACCOUNT_ADDRESS",
        ""
    )
    BLOCKCHAIN_PRIVATE_KEY: str = os.getenv(
        "BLOCKCHAIN_PRIVATE_KEY",
        ""  # 本番環境では必須
    )

    # ガス設定
    GAS_LIMIT: int = int(os.getenv("GAS_LIMIT", "3000000"))
    GAS_PRICE: int = int(os.getenv("GAS_PRICE", "20000000000"))  # 20 Gwei

    # トランザクションタイムアウト
    TX_TIMEOUT: int = int(os.getenv("TX_TIMEOUT", "120"))  # 秒
```

---

### Phase 3: フロントエンド実装

#### 3.1 型定義拡張

**ファイル**: `frontend/src/types/csi.ts`（存在しない場合は作成）

**追加内容**:
```typescript
export interface CSIData {
  id: string;
  device_id: string;
  session_id?: string;
  file_path?: string;
  file_size?: number;
  ipfs_hash?: string;
  status: string;

  // ブロックチェーン関連フィールド
  blockchain_tx_hash?: string;
  blockchain_status?: 'pending' | 'confirmed' | 'failed';
  blockchain_recorded_at?: string;

  created_at: string;
  updated_at: string;
}

export interface BlockchainInfo {
  device_id: string;
  ipfs_cid: string;
  metadata_hash: string;
  timestamp: number;
  recorder: string;
}
```

#### 3.2 APIサービス拡張

**ファイル**: `frontend/src/services/blockchain.ts`（新規作成）

```typescript
import { apiClient } from './api';

export const blockchainService = {
  // CIDから情報取得
  getCSIDataByCID: async (cid: string) => {
    const response = await apiClient.get(`/blockchain/csi-data/${cid}`);
    return response.data;
  },

  // トランザクション状態確認
  getTransactionStatus: async (txHash: string) => {
    const response = await apiClient.get(`/blockchain/transaction/${txHash}`);
    return response.data;
  },

  // ブロックチェーン記録リトライ
  retryRecord: async (csiDataId: string) => {
    const response = await apiClient.post(`/blockchain/retry-record/${csiDataId}`);
    return response.data;
  },

  // CID検証
  verifyCID: async (cid: string) => {
    const response = await apiClient.get(`/blockchain/verify/${cid}`);
    return response.data;
  },
};
```

#### 3.3 ブロックチェーン状態表示コンポーネント

**ファイル**: `frontend/src/components/BlockchainStatus.tsx`（新規作成）

```typescript
import React from 'react';

interface BlockchainStatusProps {
  txHash?: string;
  status?: 'pending' | 'confirmed' | 'failed';
  recordedAt?: string;
}

export const BlockchainStatus: React.FC<BlockchainStatusProps> = ({
  txHash,
  status,
  recordedAt,
}) => {
  if (!txHash) {
    return <span className="text-gray-500">未記録</span>;
  }

  const statusColor = {
    pending: 'text-yellow-600',
    confirmed: 'text-green-600',
    failed: 'text-red-600',
  }[status || 'pending'];

  const statusText = {
    pending: '記録中',
    confirmed: '記録完了',
    failed: '記録失敗',
  }[status || 'pending'];

  return (
    <div className="flex flex-col gap-1">
      <span className={`font-semibold ${statusColor}`}>
        {statusText}
      </span>
      <a
        href={`https://etherscan.io/tx/${txHash}`}
        target="_blank"
        rel="noopener noreferrer"
        className="text-blue-600 hover:underline text-sm"
      >
        {txHash.substring(0, 10)}...{txHash.substring(txHash.length - 8)}
      </a>
      {recordedAt && (
        <span className="text-xs text-gray-500">
          {new Date(recordedAt).toLocaleString()}
        </span>
      )}
    </div>
  );
};
```

#### 3.4 CID検索ページ

**ファイル**: `frontend/src/app/csi-data/by-cid/page.tsx`（新規作成）

```typescript
'use client';

import { useState } from 'react';
import { blockchainService } from '@/services/blockchain';
import { ipfsService } from '@/services/ipfs';

export default function CIDSearchPage() {
  const [cid, setCid] = useState('');
  const [loading, setLoading] = useState(false);
  const [blockchainInfo, setBlockchainInfo] = useState(null);
  const [csiData, setCSIData] = useState(null);

  const handleSearch = async () => {
    if (!cid) return;

    setLoading(true);
    try {
      // 1. ブロックチェーンから情報取得
      const bcInfo = await blockchainService.getCSIDataByCID(cid);
      setBlockchainInfo(bcInfo);

      // 2. IPFSからデータ取得
      const data = await ipfsService.getCSIDataPackage(cid);
      setCSIData(data);
    } catch (error) {
      console.error('CID検索エラー:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">CIDでCSIデータを検索</h1>

      <div className="flex gap-4 mb-6">
        <input
          type="text"
          value={cid}
          onChange={(e) => setCid(e.target.value)}
          placeholder="IPFS CIDを入力 (例: QmXXXXXX...)"
          className="flex-1 p-2 border rounded"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          {loading ? '検索中...' : '検索'}
        </button>
      </div>

      {blockchainInfo && (
        <div className="bg-white shadow rounded p-6 mb-4">
          <h2 className="text-xl font-semibold mb-4">ブロックチェーン情報</h2>
          {/* ブロックチェーン情報表示 */}
        </div>
      )}

      {csiData && (
        <div className="bg-white shadow rounded p-6">
          <h2 className="text-xl font-semibold mb-4">CSIデータ</h2>
          {/* CSIデータ表示 */}
        </div>
      )}
    </div>
  );
}
```

---

### Phase 4: テスト実装

#### 4.1 ユニットテスト

**ファイル**: `backend/tests/test_blockchain_service.py`（新規作成）

```python
import pytest
from app.services.blockchain_service import blockchain_service

@pytest.mark.asyncio
async def test_record_csi_data_cid():
    """CID記録テスト"""
    result = await blockchain_service.record_csi_data_cid(
        device_id="test_device_001",
        ipfs_cid="QmTest123456789",
        metadata_hash="QmMetadata123456"
    )

    assert result["tx_hash"] is not None
    assert result["status"] == "pending"

@pytest.mark.asyncio
async def test_get_csi_data_by_cid():
    """CID取得テスト"""
    cid = "QmTest123456789"
    data = await blockchain_service.get_csi_data_by_cid(cid)

    assert data is not None
    assert data["device_id"] == "test_device_001"
    assert data["ipfs_cid"] == cid
```

#### 4.2 統合テスト

**ファイル**: `backend/tests/test_csi_data_blockchain_integration.py`（新規作成）

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_full_csi_data_upload_flow():
    """CSIデータアップロード → IPFS → ブロックチェーン統合テスト"""

    # 1. ログイン
    login_response = client.post("/api/v2/auth/login", json={
        "username": "test_user",
        "password": "test_password"
    })
    token = login_response.json()["access_token"]

    # 2. CSIデータアップロード
    with open("test_data.pcap", "rb") as f:
        upload_response = client.post(
            "/api/v2/csi-data/upload-test",
            headers={"Authorization": f"Bearer {token}"},
            data={"device_id": "test_device"},
            files={"file": f}
        )

    assert upload_response.status_code == 200
    csi_data = upload_response.json()

    # 3. IPFS CIDが存在することを確認
    assert csi_data["ipfs_hash"] is not None

    # 4. ブロックチェーントランザクションハッシュが存在することを確認
    assert csi_data["blockchain_tx_hash"] is not None

    # 5. CIDでブロックチェーンから情報取得
    bc_response = client.get(
        f"/api/v2/blockchain/csi-data/{csi_data['ipfs_hash']}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert bc_response.status_code == 200
    bc_data = bc_response.json()
    assert bc_data["ipfs_cid"] == csi_data["ipfs_hash"]
```

---

### Phase 5: デプロイ・ドキュメント

#### 5.1 コントラクトデプロイスクリプト

**ファイル**: `backend/contracts/deploy.py`（新規作成）

```python
from web3 import Web3
from solcx import compile_standard, install_solc
import json

def deploy_contract():
    """スマートコントラクトをデプロイ"""

    # Solidityコンパイラのインストール
    install_solc('0.8.20')

    # コントラクトのコンパイル
    with open('CSIDataRegistry.sol', 'r') as f:
        contract_source = f.read()

    compiled = compile_standard({
        "language": "Solidity",
        "sources": {"CSIDataRegistry.sol": {"content": contract_source}},
        "settings": {
            "outputSelection": {
                "*": {"*": ["abi", "metadata", "evm.bytecode", "evm.sourceMap"]}
            }
        }
    })

    # ABIとバイトコードの取得
    contract_interface = compiled['contracts']['CSIDataRegistry.sol']['CSIDataRegistry']
    abi = contract_interface['abi']
    bytecode = contract_interface['evm']['bytecode']['object']

    # Web3接続
    w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))
    account = w3.eth.accounts[0]

    # コントラクトのデプロイ
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = Contract.constructor().transact({'from': account})
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    print(f"Contract deployed at: {tx_receipt.contractAddress}")

    # ABIとアドレスを保存
    with open('build/CSIDataRegistry.json', 'w') as f:
        json.dump({
            "address": tx_receipt.contractAddress,
            "abi": abi
        }, f, indent=2)

    return tx_receipt.contractAddress

if __name__ == "__main__":
    deploy_contract()
```

#### 5.2 セットアップガイド

**ファイル**: `docs/setup-blockchain.md`（新規作成）

内容は別途作成予定。

---

## 🔒 セキュリティ考慮事項

### 秘密鍵管理
- 環境変数で管理、`.env`ファイルはgitignore
- 本番環境ではAWS Secrets Manager等を使用
- デプロイ用アカウントは専用アカウントを使用

### ガスコスト最適化
- バッチ処理による複数CIDの一括記録
- ガスリミット・ガスプライスの適切な設定
- トランザクション失敗時のリトライロジック

### エラーハンドリング
- ブロックチェーン記録失敗時もCSIデータ保存は継続
- 非同期バックグラウンド処理でアップロードをブロックしない
- リトライAPIで手動再記録が可能

### アクセス制御
- ブロックチェーンAPI呼び出しは認証必須
- デバイス所有者のみがデータにアクセス可能
- CID検索は認証ユーザーのみ許可

---

## 📊 パフォーマンス考慮事項

### トランザクション処理
- 非同期処理によるレイテンシー削減
- バックグラウンドワーカーでの段階的処理
- Redis経由でのキューイング（将来的に実装）

### データ取得最適化
- ブロックチェーン情報をRedisにキャッシュ
- IPFS CIDの逆引き検索をPostgreSQLで高速化
- GraphQLによる必要なデータのみの取得（将来的に実装）

---

## 🧪 テスト戦略

### 開発環境
- Ganacheローカルノードでの開発・テスト
- テストネット（Goerli/Sepolia）での統合テスト
- 本番環境移行前のステージング環境テスト

### テストカバレッジ目標
- ユニットテスト: 80%以上
- 統合テスト: 主要フロー100%
- E2Eテスト: クリティカルパス100%

---

## 📈 将来的な拡張

### Layer 2統合
- Polygon、Optimism等のL2チェーンへの移行
- ガスコスト削減とトランザクション高速化

### 分散型アイデンティティ
- DIDs（Decentralized Identifiers）によるデバイス認証
- Verifiable Credentialsによるデータ検証

### DAOガバナンス
- データアクセス権限の分散管理
- コミュニティによるデータ品質評価

---

## 📝 実装チェックリスト

- [ ] スマートコントラクト作成（CSIDataRegistry.sol）
- [ ] Docker環境にGanache追加
- [ ] requirements.txtに依存関係追加
- [ ] CSIDataモデル拡張
- [ ] Alembicマイグレーション作成・実行
- [ ] blockchain_service.py実装
- [ ] csi_data.py更新（ブロックチェーン記録処理）
- [ ] スキーマ拡張（CSIDataResponse）
- [ ] blockchain.pyエンドポイント作成
- [ ] config.py設定追加
- [ ] フロントエンド型定義拡張
- [ ] BlockchainStatusコンポーネント作成
- [ ] CID検索ページ作成
- [ ] ユニットテスト作成
- [ ] 統合テスト作成
- [ ] デプロイスクリプト作成
- [ ] セットアップガイド作成
- [ ] 動作確認・デバッグ
- [ ] ドキュメント整備

---

## 🆘 トラブルシューティング

### よくある問題

#### Ganache接続エラー
```bash
# Ganacheコンテナの状態確認
docker-compose ps ganache
docker-compose logs ganache

# 再起動
docker-compose restart ganache
```

#### コントラクトデプロイ失敗
```bash
# ガス不足の場合
# config.pyでGAS_LIMITを増やす

# アカウント残高確認
python -c "from web3 import Web3; w3 = Web3(Web3.HTTPProvider('http://localhost:8545')); print(w3.eth.get_balance(w3.eth.accounts[0]))"
```

#### トランザクション pending状態が続く
```bash
# トランザクション状態確認
# blockchain APIの /transaction/{tx_hash} エンドポイントで確認

# 必要に応じて手動でリトライ
# POST /api/v2/blockchain/retry-record/{csi_data_id}
```

---

## 📚 参考資料

- [Web3.py Documentation](https://web3py.readthedocs.io/)
- [Solidity Documentation](https://docs.soliditylang.org/)
- [Ethereum JSON-RPC API](https://ethereum.org/en/developers/docs/apis/json-rpc/)
- [IPFS Documentation](https://docs.ipfs.tech/)
- [Ganache Documentation](https://trufflesuite.com/docs/ganache/)

---

**最終更新**: 2025-10-14
**バージョン**: 1.0.0
**作成者**: CSI Web Platform Development Team
