"""Full-pool CSI proof generation for the durable observation worker."""
import asyncio
import json
import os
import signal
import tempfile
import time
from pathlib import Path

from app.core.config import settings
from app.services.adaptive_csi_input import prepare_capture
from app.services.onchain_service import parse_proof


async def generate_adaptive_bundle(job):
    started = time.perf_counter()
    data, _ = await asyncio.to_thread(prepare_capture, job["raw_path"], 4004)
    preparation_ms = (time.perf_counter() - started) * 1000
    # Work files disappear after success or failure; the durable queue owns raw CSI.
    with tempfile.TemporaryDirectory(prefix="adaptive-proof-") as work:
        input_path = Path(work) / "input.json"
        output_path = Path(work) / "bundle.json"
        input_path.write_text(json.dumps(data, separators=(",", ":")))
        runner = Path(settings.ADAPTIVE_PROVER_SCRIPT)
        process = await asyncio.create_subprocess_exec(
            "node",
            "--max-old-space-size=12288",
            str(runner),
            settings.ADAPTIVE_ARTIFACT_MANIFEST,
            str(input_path),
            str(output_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env={**os.environ, "NODE_OPTIONS": "--max-old-space-size=12288"},
            start_new_session=True,
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=settings.ADAPTIVE_PROOF_TIMEOUT_SECONDS)
        except (asyncio.TimeoutError, asyncio.CancelledError) as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise RuntimeError("adaptive_proof_timeout") from None
        if process.returncode != 0 or not output_path.exists():
            raise RuntimeError("adaptive_proof_failed")
        bundle = json.loads(output_path.read_text())
        _, _, _, signals = parse_proof(bundle["proof"], bundle["publicSignals"], 70)
        if signals[1] not in (0, 1) or signals[69] != data["candidateCount"] or signals[5:69] != data["timestampsMs"]:
            raise ValueError("Adaptive proof output mismatch")
        bundle.setdefault("metrics", {})["preparationMs"] = preparation_ms
        return bundle
