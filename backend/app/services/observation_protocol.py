"""Pinned observation protocols. Existing rows always use the legacy deployment."""
import hashlib
import json
from pathlib import Path

from app.core.config import settings

ADAPTIVE = "adaptive4004"


def validate_protocol(manifest, profile="legacy"):
    if profile == "legacy":
        if (
            manifest.get("circuit", "csi_breathing_certificate") != "csi_breathing_certificate"
            or manifest.get("publicSignalCount", 1) != 1
        ):
            raise ValueError("Legacy observation protocol mismatch")
        return 1, 0
    if profile != ADAPTIVE or (
        manifest.get("circuit") != "csi_lomb_scargle_adaptive_4004"
        or manifest.get("publicSignalCount") != 70
        or manifest.get("isNormalIndex") != 1
    ):
        raise ValueError("Adaptive observation protocol mismatch")
    return 70, 1


def validate_adaptive_artifacts(deployment, deployment_path):
    validate_protocol(deployment, ADAPTIVE)
    manifest_path = Path(settings.ADAPTIVE_ARTIFACT_MANIFEST)
    artifacts = json.loads(manifest_path.read_text())
    validate_protocol(artifacts, ADAPTIVE)
    if artifacts.get("capacity") != 4004 or artifacts.get("sampleCount") != 64:
        raise ValueError("Adaptive artifact shape mismatch")
    exported = (Path(deployment_path).parent / deployment["verificationKeyFile"]).read_bytes()
    local_key = Path(artifacts["files"]["verificationKey"]).read_bytes()
    if (
        "0x" + hashlib.sha256(exported).hexdigest() != deployment["verificationKeyHash"]
        or hashlib.sha256(local_key).hexdigest() != artifacts["sha256"]["verificationKey"]
        or json.loads(exported) != json.loads(local_key)
    ):
        raise ValueError("Adaptive proving artifacts do not match deployment")
    return artifacts
