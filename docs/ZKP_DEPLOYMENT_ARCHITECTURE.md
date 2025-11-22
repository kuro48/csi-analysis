# ZKPデプロイアーキテクチャ設計書

## 📋 概要

本番デプロイ時には**ZKP回路のみ**でコサイン類似度計算を行い、JavaScript/Python実装は開発・テスト環境のみで使用します。

---

## 🏗️ アーキテクチャ構成

### 環境別の実装使用ポリシー

| 実装方式 | 開発環境 | テスト環境 | 本番環境 |
|---------|---------|-----------|---------|
| **ZKP回路（Circom）** | ✅ 使用 | ✅ 使用 | ✅ **必須** |
| **JavaScript実装** | ✅ 使用 | ✅ 使用 | ❌ 不使用 |
| **Python実装** | ✅ 使用 | ✅ 使用 | ❌ 不使用 |

### デプロイ時の処理フロー

```
【本番環境フロー】
1. CSIデータアップロード
   ↓
2. バックエンド: ZKPサービス呼び出し
   ↓
3. Circom回路でWitness生成
   ↓
4. ZKP証明生成（snarkjs groth16 prove）
   ↓
5. ZKP証明検証（snarkjs groth16 verify）
   ↓
6. 検証済み類似度をデータベース保存
   ↓
7. フロントエンド: WebSocket経由でリアルタイム表示
```

```
【開発環境フロー（追加機能）】
1. CSIデータアップロード
   ↓
2a. JavaScript直接計算（固定小数点）
2b. Python直接計算（高精度リファレンス）
2c. ZKP回路証明生成
   ↓
3. 精度比較・検証
   ↓
4. 開発用ダッシュボード表示
```

---

## 🔧 バックエンド実装

### 1. ZKPサービス（新規作成）

**ファイル**: `backend/app/services/zkp_service.py`

```python
"""
ZKP証明生成・検証サービス
本番環境ではこのサービスのみを使用
"""

import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class ZKPService:
    """ZKP証明生成・検証サービス"""

    def __init__(self):
        self.zkp_root = Path(__file__).parent.parent.parent.parent / "zkp"
        self.circuit_name = "csi_subcarrier_selector"
        self.build_dir = self.zkp_root / "build"
        self.keys_dir = self.zkp_root / "keys"
        self.proofs_dir = self.zkp_root / "proofs"

    async def generate_cosine_similarity_proof(
        self,
        reference_vector: List[int],
        candidate_vectors: List[List[int]],
        scale: int = 10000
    ) -> Dict[str, Any]:
        """
        コサイン類似度のZKP証明を生成

        Args:
            reference_vector: 参照ベクトル（Pythagorean triple近似済み）
            candidate_vectors: 候補ベクトルリスト
            scale: 固定小数点スケール（デフォルト: 10000）

        Returns:
            {
                "proof": ZKP証明,
                "publicSignals": 公開信号,
                "bestIndex": 最適サブキャリアインデックス,
                "bestSimilarity": 最大類似度
            }
        """
        try:
            # 1. Witness生成用の入力データ準備
            input_data = self._prepare_witness_input(
                reference_vector,
                candidate_vectors,
                scale
            )

            # 2. Witness生成
            witness_file = await self._generate_witness(input_data)

            # 3. ZKP証明生成
            proof, public_signals = await self._generate_proof(witness_file)

            # 4. 結果パース
            best_index = int(public_signals[0])
            best_similarity = int(public_signals[1])

            return {
                "proof": proof,
                "publicSignals": public_signals,
                "bestIndex": best_index,
                "bestSimilarity": best_similarity,
                "normalizedSimilarity": best_similarity / scale
            }

        except Exception as e:
            logger.error(f"ZKP proof generation failed: {e}")
            raise

    async def verify_proof(
        self,
        proof: Dict[str, Any],
        public_signals: List[int]
    ) -> bool:
        """
        ZKP証明を検証

        Args:
            proof: ZKP証明
            public_signals: 公開信号

        Returns:
            True: 検証成功, False: 検証失敗
        """
        try:
            # 証明ファイルを一時保存
            temp_proof_file = self.proofs_dir / "temp_proof.json"
            temp_public_file = self.proofs_dir / "temp_public.json"

            with open(temp_proof_file, 'w') as f:
                json.dump(proof, f)

            with open(temp_public_file, 'w') as f:
                json.dump(public_signals, f)

            # snarkjs groth16 verify 実行
            verification_key = self.keys_dir / f"{self.circuit_name}_verification_key.json"

            result = subprocess.run(
                [
                    "snarkjs", "groth16", "verify",
                    str(verification_key),
                    str(temp_public_file),
                    str(temp_proof_file)
                ],
                capture_output=True,
                text=True,
                check=True
            )

            # 検証結果パース
            is_valid = "OK" in result.stdout

            logger.info(f"ZKP verification result: {is_valid}")
            return is_valid

        except Exception as e:
            logger.error(f"ZKP verification failed: {e}")
            return False
        finally:
            # 一時ファイル削除
            if temp_proof_file.exists():
                temp_proof_file.unlink()
            if temp_public_file.exists():
                temp_public_file.unlink()

    def _prepare_witness_input(
        self,
        reference: List[int],
        candidates: List[List[int]],
        scale: int
    ) -> Dict[str, Any]:
        """Witness生成用の入力データを準備"""
        # ノルム計算
        def calculate_norm(vec):
            return int((sum(x**2 for x in vec)) ** 0.5)

        # 類似度計算
        def calculate_similarity(vec_a, vec_b):
            dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
            norm_a = calculate_norm(vec_a)
            norm_b = calculate_norm(vec_b)

            if norm_a == 0 or norm_b == 0:
                return 0, norm_a, norm_b, dot_product

            similarity = round((dot_product * scale) / (norm_a * norm_b))
            return similarity, norm_a, norm_b, dot_product

        # 各候補の類似度を計算
        ref_norm = calculate_norm(reference)
        candidate_data = []

        for cand in candidates:
            sim, _, cand_norm, dot_prod = calculate_similarity(reference, cand)
            candidate_data.append({
                "vector": cand,
                "norm": cand_norm,
                "similarity": sim,
                "dotProduct": dot_prod
            })

        # 入力データ構築
        return {
            "reference": reference,
            "refNorm": ref_norm,
            "candidates": [c["vector"] for c in candidate_data],
            "candNorms": [c["norm"] for c in candidate_data],
            "similarities": [c["similarity"] for c in candidate_data],
            "dotProducts": [c["dotProduct"] for c in candidate_data]
        }

    async def _generate_witness(self, input_data: Dict[str, Any]) -> Path:
        """Witness生成"""
        input_file = self.build_dir / "input.json"
        witness_file = self.build_dir / f"{self.circuit_name}_js" / "witness.wtns"

        # 入力データ保存
        with open(input_file, 'w') as f:
            json.dump(input_data, f)

        # Witness生成実行
        subprocess.run(
            [
                "node",
                str(self.build_dir / f"{self.circuit_name}_js" / "generate_witness.js"),
                str(self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"),
                str(input_file),
                str(witness_file)
            ],
            check=True,
            capture_output=True
        )

        return witness_file

    async def _generate_proof(self, witness_file: Path) -> tuple:
        """ZKP証明生成"""
        proof_file = self.proofs_dir / "proof.json"
        public_file = self.proofs_dir / "public.json"
        zkey_file = self.keys_dir / f"{self.circuit_name}_final.zkey"

        # snarkjs groth16 prove 実行
        subprocess.run(
            [
                "snarkjs", "groth16", "prove",
                str(zkey_file),
                str(witness_file),
                str(proof_file),
                str(public_file)
            ],
            check=True,
            capture_output=True
        )

        # 証明と公開信号を読み込み
        with open(proof_file) as f:
            proof = json.load(f)

        with open(public_file) as f:
            public_signals = json.load(f)

        return proof, public_signals


# シングルトンインスタンス
zkp_service = ZKPService()
```

---

### 2. CSIデータサービス統合

**ファイル**: `backend/app/services/csi_data.py`（修正）

```python
# 既存のインポートに追加
from app.services.zkp_service import zkp_service
from app.core.config import settings

class CSIDataService:

    @staticmethod
    async def process_csi_with_zkp(
        db: Session,
        csi_data_id: uuid.UUID,
        reference_vector: List[int],
        candidate_vectors: List[List[int]]
    ) -> Dict[str, Any]:
        """
        ZKP回路でCSIサブキャリア選択を実行
        本番環境ではこの関数のみを使用
        """
        try:
            # 1. ZKP証明生成
            proof_result = await zkp_service.generate_cosine_similarity_proof(
                reference_vector,
                candidate_vectors
            )

            # 2. ZKP証明検証
            is_valid = await zkp_service.verify_proof(
                proof_result["proof"],
                proof_result["publicSignals"]
            )

            if not is_valid:
                raise ValueError("ZKP proof verification failed")

            # 3. 検証済み結果をデータベース保存
            csi_data = db.query(CSIData).filter(CSIData.id == csi_data_id).first()
            if csi_data:
                processed_data = {
                    "zkp_proof": proof_result["proof"],
                    "best_subcarrier_index": proof_result["bestIndex"],
                    "similarity": proof_result["normalizedSimilarity"],
                    "verified_at": datetime.utcnow().isoformat()
                }

                csi_data.processed_data = json.dumps(processed_data)
                csi_data.status = "verified"
                db.commit()

            return proof_result

        except Exception as e:
            logger.error(f"ZKP processing failed for CSI data {csi_data_id}: {e}")
            raise
```

---

### 3. APIエンドポイント追加

**ファイル**: `backend/app/api/endpoints/zkp.py`（新規作成）

```python
"""
ZKP関連APIエンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.services.zkp_service import zkp_service
from app.schemas.zkp import (
    ZKPProofRequest, ZKPProofResponse, ZKPVerifyRequest
)

router = APIRouter()


@router.post("/generate-proof", response_model=ZKPProofResponse)
async def generate_zkp_proof(
    request: ZKPProofRequest,
    current_user: User = Depends(get_current_user)
):
    """
    ZKP証明を生成
    本番環境ではこのエンドポイントを使用
    """
    try:
        result = await zkp_service.generate_cosine_similarity_proof(
            reference_vector=request.reference_vector,
            candidate_vectors=request.candidate_vectors,
            scale=request.scale
        )

        return ZKPProofResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ZKP proof generation failed: {str(e)}")


@router.post("/verify-proof")
async def verify_zkp_proof(
    request: ZKPVerifyRequest,
    current_user: User = Depends(get_current_user)
):
    """ZKP証明を検証"""
    try:
        is_valid = await zkp_service.verify_proof(
            proof=request.proof,
            public_signals=request.public_signals
        )

        return {
            "valid": is_valid,
            "message": "Proof is valid" if is_valid else "Proof is invalid"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ZKP verification failed: {str(e)}")
```

---

## 📦 環境別設定

### 環境変数設定

**ファイル**: `backend/.env`

```bash
# ZKP設定
ZKP_ENABLED=true                    # 本番: true, 開発: true
ZKP_DEVELOPMENT_MODE=false          # 本番: false, 開発: true
ZKP_ALLOW_DIRECT_CALCULATION=false  # 本番: false, 開発: true

# 開発専用: JavaScript/Python直接計算を許可
ALLOW_JS_SIMILARITY=false           # 本番: false, 開発: true
ALLOW_PYTHON_SIMILARITY=false       # 本番: false, 開発: true
```

### 設定クラス

**ファイル**: `backend/app/core/config.py`（追加）

```python
class Settings(BaseSettings):
    # ... 既存の設定 ...

    # ZKP設定
    zkp_enabled: bool = True
    zkp_development_mode: bool = False
    zkp_allow_direct_calculation: bool = False

    # 開発専用設定
    allow_js_similarity: bool = False
    allow_python_similarity: bool = False
```

---

## 🚀 デプロイ手順

### 1. ZKP回路のセットアップ

```bash
cd zkp

# 1. 回路コンパイル
npm run compile:csi_selector

# 2. Trusted Setup
npm run setup:csi_selector

# 3. キーとビルド成果物を本番環境にコピー
# - build/csi_subcarrier_selector_js/
# - keys/csi_subcarrier_selector_final.zkey
# - keys/csi_subcarrier_selector_verification_key.json
```

### 2. 本番環境構成

```
production/
├── backend/
│   ├── app/
│   │   └── services/
│   │       └── zkp_service.py  ✅ ZKPサービスのみ
│   └── .env                     # ZKP_DEVELOPMENT_MODE=false
├── zkp/
│   ├── build/
│   │   └── csi_subcarrier_selector_js/  ✅ 本番ビルド
│   └── keys/                             ✅ 本番キー
└── scripts/                              ❌ 開発用スクリプト除外
    ├── calculate_all_subcarrier_similarity.js  ❌
    ├── compare_similarity_accuracy.py          ❌
    └── prove_from_all_subcarriers.js           ❌
```

### 3. Docker構成（本番環境）

**ファイル**: `docker-compose.prod.yml`

```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.prod
    environment:
      - ZKP_ENABLED=true
      - ZKP_DEVELOPMENT_MODE=false
      - ALLOW_JS_SIMILARITY=false
      - ALLOW_PYTHON_SIMILARITY=false
    volumes:
      - ./zkp/build:/app/zkp/build:ro         # 読み取り専用
      - ./zkp/keys:/app/zkp/keys:ro           # 読み取り専用
      - ./zkp/proofs:/app/zkp/proofs          # 証明保存用
```

---

## 🧪 開発環境での並行使用

開発環境では全ての実装を使用可能:

```bash
# 環境変数設定（開発環境）
ZKP_DEVELOPMENT_MODE=true
ALLOW_JS_SIMILARITY=true
ALLOW_PYTHON_SIMILARITY=true

# 精度比較テスト
cd zkp
node scripts/calculate_all_subcarrier_similarity.js
python scripts/compare_similarity_accuracy.py

# ZKP証明生成テスト
node scripts/prove_from_all_subcarriers.js
```

---

## ✅ チェックリスト

### 本番デプロイ前

- [ ] ZKP回路のコンパイル完了
- [ ] Trusted Setup完了
- [ ] ZKPサービス実装完了
- [ ] APIエンドポイント実装完了
- [ ] 環境変数が本番設定（`ZKP_DEVELOPMENT_MODE=false`）
- [ ] 開発用スクリプトがデプロイパッケージから除外
- [ ] ZKP証明の生成・検証テスト完了
- [ ] パフォーマンステスト完了

### セキュリティ

- [ ] ZKPキーファイルの読み取り専用化
- [ ] 開発用エンドポイントの無効化
- [ ] 直接計算APIの無効化（`ALLOW_*=false`）
- [ ] ZKP証明の改ざん検証テスト完了

---

## 📊 パフォーマンス目標

| 指標 | 目標値 | 測定方法 |
|-----|-------|---------|
| ZKP証明生成時間 | < 2秒 | APIレスポンスタイム |
| ZKP検証時間 | < 100ms | 検証処理時間 |
| メモリ使用量 | < 512MB | Witness生成ピーク |
| 並列処理数 | 10証明/秒 | 同時リクエスト処理 |

---

## 🔄 移行計画

### Phase 1: 並行運用期間（開発環境）
- JavaScript/Python実装 + ZKP回路を並行使用
- 精度・パフォーマンスの比較検証

### Phase 2: ZKP優先期間（ステージング環境）
- ZKP回路をメイン処理に変更
- JavaScript/Python実装はバックアップとして保持

### Phase 3: 本番デプロイ
- **ZKP回路のみ**で運用開始
- 開発用実装は本番環境から完全除外

---

## 📝 まとめ

本番環境では:
- ✅ **ZKP回路のみ**でコサイン類似度計算
- ✅ プライバシー保護とセキュリティ確保
- ✅ 検証可能な証明生成

開発環境では:
- ✅ JavaScript/Python実装も使用可能
- ✅ 精度比較とデバッグ支援
- ✅ 柔軟な開発ワークフロー

このアーキテクチャにより、**本番環境のセキュリティ**と**開発効率**を両立します。
