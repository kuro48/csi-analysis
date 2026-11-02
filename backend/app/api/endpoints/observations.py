"""Patient catalog and result verification; authenticated capture ingestion."""
import hashlib
import logging
import os
import secrets
import tempfile
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile

from app.core.config import settings
from app.services.observation_chain import ObservationChain
from app.services.observation_store import ObservationStore, QueueFull
from app.services.onchain_service import ChainUnavailable

logger = logging.getLogger(__name__)
router = APIRouter()


def operator(authorization: str = Header(default="")):
    # Capture registration never falls back to anonymous writes, even in DEBUG.
    if not settings.OPERATOR_API_TOKEN or not secrets.compare_digest(
        authorization, "Bearer " + settings.OPERATOR_API_TOKEN
    ):
        raise HTTPException(401, "収集操作には運用者トークンが必要です", headers={"WWW-Authenticate": "Bearer"})


def store():
    return ObservationStore()


def no_cache(response: Response):
    response.headers["Cache-Control"] = "no-store"


@router.get("/patients", dependencies=[Depends(no_cache)])
def patients(db=Depends(store)):
    return {"patients": db.patients()}


@router.post("/patients", status_code=201, dependencies=[Depends(operator), Depends(no_cache)])
def add_patient(db=Depends(store)):
    return db.add_patient()


@router.get("/patients/{patient_id}/measurements", dependencies=[Depends(no_cache)])
def measurements(
    patient_id: UUID, start_at: int = Query(0, ge=0), end_at: int = Query(253402300799, ge=1), db=Depends(store)
):
    if not db.patient_exists(str(patient_id)):
        raise HTTPException(404, "患者が見つかりません")
    if end_at <= start_at:
        raise HTTPException(422, "計測期間の範囲が不正です")
    return {"measurements": db.observations(str(patient_id), start_at, end_at)}


@router.post("/captures", status_code=202, dependencies=[Depends(operator), Depends(no_cache)])
async def capture(
    patient_id: UUID = Form(...),
    capture_id: UUID = Form(...),
    observed_at: datetime = Form(...),
    duration_seconds: int = Form(..., ge=1, le=3600),
    file: UploadFile = File(...),
    db=Depends(store),
):
    if observed_at.tzinfo is None:
        raise HTTPException(422, "計測開始時刻にはタイムゾーンが必要です")
    timestamp = int(observed_at.timestamp())
    if timestamp <= 0 or timestamp + duration_seconds > time.time() + 300:
        raise HTTPException(422, "計測時刻・期間を確認してください")
    if not db.patient_exists(str(patient_id)):
        raise HTTPException(404, "患者が見つかりません")
    if Path(file.filename or "").suffix.lower() != ".csi":
        raise HTTPException(422, "PicoScenes .csiファイルが必要です")
    path = None
    try:
        digest = hashlib.sha256()
        size = 0
        with tempfile.NamedTemporaryFile(dir=db.raw, suffix=".csi", delete=False) as target:
            path = Path(target.name)
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 50 * 1024 * 1024:
                    raise HTTPException(413, "CSIは50 MB以下にしてください")
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if not size:
            raise HTTPException(422, "CSIファイルが空です")
        try:
            job = db.enqueue(str(capture_id), str(patient_id), timestamp, duration_seconds, digest.hexdigest(), path)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except QueueFull as exc:
            raise HTTPException(429, str(exc), headers={"Retry-After": "60"}) from exc
        if job["raw_path"] == str(path):
            path = None  # Queue owns this file until proof generation/retention expiry.
        return {"id": job["id"], "status": job["status"]}
    finally:
        if path:
            path.unlink(missing_ok=True)
        await file.close()


@router.get("/captures/{capture_id}", dependencies=[Depends(operator), Depends(no_cache)])
def capture_status(capture_id: UUID, db=Depends(store)):
    job = db.capture(str(capture_id))
    if not job:
        raise HTTPException(404, "収集が見つかりません")
    return {key: job[key] for key in ("id", "status", "attempts", "error", "tx_hash")}


@router.post("/captures/{capture_id}/retry", dependencies=[Depends(operator), Depends(no_cache)])
def retry(capture_id: UUID, db=Depends(store)):
    job = db.capture(str(capture_id))
    if not job or job["status"] != "failed":
        raise HTTPException(409, "再試行できる失敗ジョブがありません")
    if not job["bundle"] and not Path(job["raw_path"]).exists():
        raise HTTPException(410, "CSIの保存期限を過ぎています。再収集してください")
    # Never clear a signed transaction: an uncertain broadcast must not be re-signed.
    db.update(job["id"], status="queued", attempts=0, next_attempt=0, error=None)
    return {"id": job["id"], "status": "queued"}


@router.post("/measurements/{capture_id}/verify", dependencies=[Depends(no_cache)])
def verify(capture_id: UUID, response: Response, db=Depends(store)):
    job = db.capture(str(capture_id))
    if not job:
        raise HTTPException(404, "計測が見つかりません")
    if not job["tx_hash"]:
        response.status_code = 202
        return {"status": job["status"]}  # No result, especially no default false.
    try:
        result = ObservationChain().result(job)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ChainUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception:
        logger.exception("Observation verification unavailable")
        raise HTTPException(503, "チェーンに接続できません。判定結果は表示しません")
    if result["status"] != "verified":
        response.status_code = 202
    return result
