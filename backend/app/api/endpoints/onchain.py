import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

from app.services.onchain_service import ChainUnavailable, OnchainService

router = APIRouter()
logger = logging.getLogger(__name__)
HASH_PATTERN = r"^0x[0-9a-fA-F]{64}$"


class PrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    circuit: str = Field(pattern=r"^csi_[a-z0-9_]+$", max_length=100)
    proof: dict[str, Any]
    publicSignals: list[str] = Field(min_length=1, max_length=256)


def get_onchain_service():
    try:
        return OnchainService()
    except ChainUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/status")
def status():
    try:
        return OnchainService().status()
    except ChainUnavailable as exc:
        return {"connected": False, "message": str(exc), "circuits": []}
    except Exception:
        logger.exception("Chain status failed")
        raise HTTPException(503, "チェーンの状態を取得できません")


def invoke(operation):
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        logger.exception("Onchain RPC operation failed")
        raise HTTPException(503, "ブロックチェーンへの接続を確認して再試行してください")


@router.post("/prepare")
def prepare(body: PrepareRequest, service=Depends(get_onchain_service)):
    return invoke(lambda: service.prepare(body.circuit, body.proof, body.publicSignals))


@router.get("/transactions/{tx_hash}")
def receipt(tx_hash: str = Path(pattern=HASH_PATTERN), service=Depends(get_onchain_service)):
    return invoke(lambda: service.receipt(tx_hash))


@router.get("/proofs/{proof_id}")
def record(proof_id: str = Path(pattern=HASH_PATTERN), service=Depends(get_onchain_service)):
    return invoke(lambda: service.record(proof_id))
