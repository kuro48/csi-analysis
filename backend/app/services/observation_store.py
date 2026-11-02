"""Durable single-host capture queue. Proofs persist; raw CSI is temporary."""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


class QueueFull(RuntimeError):
    pass


class ObservationStore:
    def __init__(self):
        self.root = Path(settings.OBSERVATION_DATA_DIR).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.raw = self.root / "raw"
        self.raw.mkdir(exist_ok=True, mode=0o700)
        self.path = self.root / "observations.sqlite3"
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS patients (
                    id TEXT PRIMARY KEY, label TEXT NOT NULL, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS captures (
                    id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
                    observed_at INTEGER NOT NULL, duration INTEGER NOT NULL, digest TEXT NOT NULL,
                    raw_path TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                    bundle TEXT, tx_hash TEXT, signed_tx TEXT, error TEXT,
                    chain_id INTEGER, registry TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0, next_attempt INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS patient_time ON captures(patient_id, observed_at);
            """
            )
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def patients(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM patients ORDER BY created_at, id LIMIT 1000")]

    def add_patient(self):
        patient_id = str(uuid4())
        with self.connect() as db:
            # No names/DOB/medical record numbers are accepted by the public catalog.
            db.execute("INSERT INTO patients VALUES (?, ?, ?)", (patient_id, "患者 " + patient_id[:8], int(time.time())))
        return {"id": patient_id, "label": "患者 " + patient_id[:8]}

    def patient_exists(self, patient_id):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone() is not None

    def capture(self, capture_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM captures WHERE id=?", (capture_id,)).fetchone()
            return dict(row) if row else None

    def enqueue(self, capture_id, patient_id, observed_at, duration, digest, raw_path):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT 1 FROM captures WHERE id=?", (capture_id,)).fetchone()
            count = db.execute(
                "SELECT COUNT(*) FROM captures WHERE status IN ('queued','processing','submitted')"
            ).fetchone()[0]
            if not existing and count >= settings.OBSERVATION_MAX_PENDING:
                raise QueueFull("収集キューが満杯です。後で同じ収集IDで再送してください")
            db.execute(
                "INSERT OR IGNORE INTO captures (id,patient_id,observed_at,duration,digest,raw_path,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (capture_id, patient_id, observed_at, duration, digest, str(raw_path), int(time.time())),
            )
            row = dict(db.execute("SELECT * FROM captures WHERE id=?", (capture_id,)).fetchone())
            if (row["patient_id"], row["observed_at"], row["duration"], row["digest"]) != (
                patient_id,
                observed_at,
                duration,
                digest,
            ):
                raise ValueError("同じ収集IDに異なるデータが指定されています")
            return row

    def observations(self, patient_id, start_at=0, end_at=253402300799):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,patient_id,observed_at,duration,status FROM captures WHERE patient_id=? "
                    "AND observed_at>=? AND observed_at<? ORDER BY observed_at DESC, id LIMIT 2000",
                    (patient_id, start_at, end_at),
                )
            ]

    def update(self, capture_id, **fields):
        allowed = {
            "status",
            "bundle",
            "tx_hash",
            "signed_tx",
            "error",
            "attempts",
            "next_attempt",
            "chain_id",
            "registry",
        }
        if not fields or fields.keys() - allowed:
            raise ValueError("Invalid capture update")
        with self.connect() as db:
            db.execute(
                "UPDATE captures SET " + ",".join(f"{key}=?" for key in fields) + " WHERE id=?",
                [*fields.values(), capture_id],
            )

    def next_job(self):
        with self.connect() as db:
            # One recorder nonce stream. An uncertain broadcast must settle before
            # another capture can sign; otherwise a stale RPC nonce could replace it.
            signed = db.execute(
                "SELECT * FROM captures WHERE signed_tx IS NOT NULL ORDER BY created_at,id LIMIT 1"
            ).fetchone()
            if signed:
                if signed["status"] == "failed" or signed["next_attempt"] > int(time.time()):
                    return None
                return dict(signed)
            row = db.execute(
                "SELECT * FROM captures WHERE status IN ('queued','processing','submitted') "
                "AND next_attempt<=? ORDER BY created_at,id LIMIT 1",
                (int(time.time()),),
            ).fetchone()
            return dict(row) if row else None

    def save_bundle(self, job, bundle):
        self.update(job["id"], bundle=json.dumps(bundle), status="processing")
        Path(job["raw_path"]).unlink(missing_ok=True)

    def expire_raw(self):
        cutoff = int(time.time()) - settings.OBSERVATION_RAW_RETENTION_HOURS * 3600
        with self.connect() as db:
            rows = db.execute("SELECT id,raw_path,bundle,status FROM captures WHERE created_at<?", (cutoff,)).fetchall()
            for row in rows:
                Path(row["raw_path"]).unlink(missing_ok=True)
                if row["bundle"] is None and row["status"] in ("queued", "processing"):
                    db.execute("UPDATE captures SET status='failed',error='raw_expired' WHERE id=?", (row["id"],))
        # Covers a process crash after upload, before queue commit.
        for path in self.raw.glob("*.csi"):
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
