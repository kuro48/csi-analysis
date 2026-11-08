#!/usr/bin/env python3
"""PicoScenes capture -> durable local spool -> authenticated observation queue.

Standard library only. CSI_PATIENT_ID / CSI_SERVER_URL / CSI_OPERATOR_TOKEN_FILE
must be configured. Run --retry-only after network failures, or --loop for
continuous acquisition. Existing debug upload/capture scripts are unchanged.
"""
import argparse
from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.parse import urlsplit
from uuid import UUID, uuid4


def upload(server, token, metadata, path):
    url = urlsplit(server)
    if url.scheme not in ("https", "http") or url.username or url.password or url.query or url.fragment:
        raise ValueError("CSI_SERVER_URL must be an HTTPS origin")
    if url.scheme != "https" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("HTTPS is required outside loopback")
    boundary = uuid4().hex
    fields = b""
    metadata = {"ledger": "evm", "proof_profile": "legacy", **metadata}
    for key in ("ledger", "proof_profile", "patient_id", "capture_id", "observed_at", "duration_seconds"):
        fields += (f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{metadata[key]}\r\n').encode()
    fields += (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="capture.csi"\r\nContent-Type: application/octet-stream\r\n\r\n'
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    size = path.stat().st_size
    if not 0 < size <= 50 * 1024 * 1024:
        raise ValueError("CSI must be between 1 byte and 50 MB")
    factory = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    conn = factory(url.hostname, url.port, timeout=120)
    try:
        conn.putrequest("POST", url.path.rstrip("/") + "/api/v2/observations/captures")
        conn.putheader("Authorization", "Bearer " + token)
        conn.putheader("Content-Type", "multipart/form-data; boundary=" + boundary)
        conn.putheader("Content-Length", str(len(fields) + size + len(tail)))
        conn.endheaders()
        conn.send(fields)
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                conn.send(chunk)
        conn.send(tail)
        response = conn.getresponse()
        body = response.read(65536)
        if response.status not in (200, 202):
            raise RuntimeError(f"Upload failed: HTTP {response.status}; capture remains in spool")
        data = json.loads(body)
        if data.get("id") != metadata["capture_id"]:
            raise RuntimeError("Unexpected capture acknowledgement")
        return data
    finally:
        conn.close()


def flush(spool, server, token):
    cutoff = time.time() - max(1, int(os.environ.get("CSI_SPOOL_RETENTION_HOURS", "24"))) * 3600
    for raw in spool.glob("*.csi"):
        if raw.stat().st_mtime < cutoff:
            raw.with_suffix(".json").unlink(missing_ok=True)
            raw.unlink(missing_ok=True)
            print("Expired an unsent capture; acquire a new measurement.", flush=True)
    for info in sorted(spool.glob("*.json")):
        metadata = json.loads(info.read_text())
        csi = info.with_suffix(".csi")
        reply = upload(server, token, metadata, csi)
        # Server now owns durable delivery. Never print keys, raw data or proof.
        print(f'Accepted capture {reply["id"]}: {reply["status"]}', flush=True)
        info.unlink()
        csi.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--retry-only", action="store_true")
    parser.add_argument("--file", type=Path, help="Debug: copy existing CSI into the capture spool")
    parser.add_argument("--observed-at", help="Required with --file; ISO8601 with timezone")
    args = parser.parse_args()
    os.umask(0o077)
    patient = str(UUID(os.environ["CSI_PATIENT_ID"]))
    server = os.environ["CSI_SERVER_URL"]
    token_file = Path(os.environ["CSI_OPERATOR_TOKEN_FILE"])
    if token_file.stat().st_mode & 0o077:
        raise ValueError("Token file must have mode 0600")
    token = token_file.read_text().strip()
    if len(token) < 32:
        raise ValueError("Use an operator token of at least 32 characters")
    spool = Path(os.environ.get("CSI_OBSERVATION_SPOOL", str(Path.home() / ".csi-observation-spool"))).resolve()
    spool.mkdir(parents=True, exist_ok=True, mode=0o700)
    duration = int(os.environ.get("CSI_MAIN_DURATION", "60"))
    if not 1 <= duration <= 3600:
        raise ValueError("Capture duration must be between 1 and 3600 seconds")
    if args.file and (not args.observed_at or args.loop):
        raise ValueError("--file requires --observed-at and cannot be combined with --loop")
    # Keep one hardware capture loop and spool sender per device.
    import fcntl

    with (spool / "capture.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            flush(spool, server, token)
            if args.retry_only:
                return
            capture_id = str(uuid4())
            path = spool / (capture_id + ".csi")
            observed = datetime.now(timezone.utc)
            if args.file:
                observed = datetime.fromisoformat(args.observed_at.replace("Z", "+00:00"))
                if observed.tzinfo is None:
                    raise ValueError("--observed-at requires a timezone")
                shutil.copyfile(args.file, path)
            else:
                if any(char.isspace() for char in str(spool)):
                    raise ValueError("PicoScenes spool path must not contain whitespace")
                nic = int(os.environ.get("CSI_NIC_INDEX", "2"))
                bandwidth = int(os.environ.get("CSI_CBW", "160"))
                command = (
                    f"-d debug -i {nic} --mode logger --cbw {bandwidth} --output {path.with_suffix('')} -q {duration}"
                )
                with (spool / "picoscenes.log").open("w") as log:
                    subprocess.run(
                        ["PicoScenes", command], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=duration + 30
                    )
            if not path.exists() or not path.stat().st_size:
                raise RuntimeError("PicoScenes produced no CSI")
            metadata = {
                "capture_id": capture_id,
                "patient_id": patient,
                "observed_at": observed.isoformat(),
                "duration_seconds": duration,
                "ledger": os.environ.get("CSI_LEDGER", "evm"),
                "proof_profile": os.environ.get("CSI_PROOF_PROFILE", "legacy"),
            }
            temporary = path.with_suffix(".tmp")
            with temporary.open("w") as out:
                json.dump(metadata, out)
                out.flush()
                os.fsync(out.fileno())
            temporary.replace(path.with_suffix(".json"))
            flush(spool, server, token)
            if not args.loop:
                return
            time.sleep(1)


if __name__ == "__main__":
    main()
