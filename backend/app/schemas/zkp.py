"""
ZKP関連のPydanticスキーマ
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime


class ZKPProofRequest(BaseModel):
    """ZKP証明生成リクエスト"""

    analysisIds: List[str] = Field(..., description="呼吸解析結果IDのリスト")


class ZKPProofMetadata(BaseModel):
    """ZKP証明のメタデータ"""

    breathingRate: float = Field(..., description="呼吸数（回/分）")
    confidenceScore: float = Field(..., description="信頼度スコア（0.0-1.0）")
    timestamp: str = Field(..., description="タイムスタンプ（ISO形式）")
    protocol: str = Field(default="Groth16", description="証明プロトコル")
    curve: str = Field(default="bn128", description="楕円曲線")


class ZKPProofResponse(BaseModel):
    """ZKP証明生成レスポンス"""

    analysisId: str = Field(..., description="呼吸解析結果ID")
    proof: Dict[str, Any] = Field(..., description="ZKP証明データ")
    publicSignals: List[str] = Field(..., description="公開入力シグナル")
    commitment: str = Field(..., description="CSIデータのコミットメント")
    metadata: ZKPProofMetadata = Field(..., description="証明のメタデータ")

    class Config:
        json_schema_extra = {
            "example": {
                "analysisId": "550e8400-e29b-41d4-a716-446655440000",
                "proof": {
                    "pi_a": ["...", "...", "..."],
                    "pi_b": [["...", "..."], ["...", "..."], ["...", "..."]],
                    "pi_c": ["...", "...", "..."],
                    "protocol": "groth16",
                    "curve": "bn128",
                },
                "publicSignals": [
                    "12345678901234567890",  # csiCommitment
                    "15",  # breathingRate
                    "85",  # confidenceScore
                    "1234567890",  # timestamp
                ],
                "commitment": "12345678901234567890",
                "metadata": {
                    "breathingRate": 15.0,
                    "confidenceScore": 0.85,
                    "timestamp": "2024-10-28T00:00:00Z",
                    "protocol": "Groth16",
                    "curve": "bn128",
                },
            }
        }


class ZKPVerifyRequest(BaseModel):
    """ZKP証明検証リクエスト"""

    proof: Dict[str, Any] = Field(..., description="ZKP証明データ")
    publicSignals: List[str] = Field(..., description="公開入力シグナル")


class ZKPVerifyResponse(BaseModel):
    """ZKP証明検証レスポンス"""

    isValid: bool = Field(..., description="検証結果（True: 有効, False: 無効）")
    publicSignals: List[str] = Field(..., description="公開入力シグナル")
    message: str = Field(..., description="検証結果メッセージ")

    class Config:
        json_schema_extra = {
            "example": {
                "isValid": True,
                "publicSignals": [
                    "12345678901234567890",
                    "15",
                    "85",
                    "1234567890",
                ],
                "message": "Proof is valid",
            }
        }


class ZKPStats(BaseModel):
    """ZKP統計情報"""

    totalProofsGenerated: int = Field(
        ..., description="生成された証明の総数"
    )
    averageGenerationTime: float = Field(
        ..., description="平均証明生成時間（秒）"
    )
    averageVerificationTime: float = Field(
        ..., description="平均検証時間（秒）"
    )
    successRate: float = Field(..., description="成功率（0.0-1.0）")


class ZKPBatchProofRequest(BaseModel):
    """ZKPバッチ証明生成リクエスト"""

    startTime: Optional[datetime] = Field(None, description="開始時刻")
    endTime: Optional[datetime] = Field(None, description="終了時刻")
    maxResults: int = Field(default=10, description="最大結果数", ge=1, le=100)


class ZKPBlockchainSubmitRequest(BaseModel):
    """ZKP証明のブロックチェーン提出リクエスト"""

    proof: Dict[str, Any] = Field(..., description="ZKP証明データ")
    publicSignals: List[str] = Field(..., description="公開入力シグナル")
    ipfsHash: Optional[str] = Field(None, description="IPFSハッシュ（オプション）")


class ZKPBlockchainSubmitResponse(BaseModel):
    """ZKP証明のブロックチェーン提出レスポンス"""

    transactionHash: str = Field(..., description="トランザクションハッシュ")
    blockNumber: Optional[int] = Field(None, description="ブロック番号")
    gasUsed: Optional[int] = Field(None, description="使用ガス量")
    status: str = Field(..., description="トランザクションステータス")
    ipfsHash: Optional[str] = Field(None, description="IPFSハッシュ")

    class Config:
        json_schema_extra = {
            "example": {
                "transactionHash": "0x1234567890abcdef...",
                "blockNumber": 12345678,
                "gasUsed": 150000,
                "status": "confirmed",
                "ipfsHash": "QmX...",
            }
        }
