"""Bind a Linux-built prover to transferred circuit keys without rerunning setup."""
import hashlib
import json
import os
from pathlib import Path
import sys

os.umask(0o077)
if os.environ.get("ADAPTIVE_ARTIFACT_MANIFEST"):
    source = Path("/artifacts/artifacts.json")
    manifest = json.loads(source.read_text())
    if manifest.get("prover") != "arkworks-0.5":
        raise ValueError("Staging image requires arkworks artifacts")
    prover = Path("/usr/local/bin/csi-native-prover")
    manifest["files"]["prover"] = str(prover)
    manifest["sha256"]["prover"] = hashlib.sha256(prover.read_bytes()).hexdigest()
    Path(os.environ["ADAPTIVE_ARTIFACT_MANIFEST"]).write_text(json.dumps(manifest))
if len(sys.argv) < 2:
    raise ValueError("Missing runtime command")
os.execvp(sys.argv[1], sys.argv[1:])
