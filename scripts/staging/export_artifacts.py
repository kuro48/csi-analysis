"""Copy pinned portable artifacts; never copy Mac binaries or generate new keys."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def export(source: Path, destination: Path):
    manifest = json.loads(source.read_text())
    if (manifest.get("prover"), manifest.get("circuit"), manifest.get("publicSignalCount")) != (
        "arkworks-0.5", "csi_lomb_scargle_adaptive_4004", 70
    ):
        raise ValueError("Expected stable adaptive4004 native artifacts")
    if destination.exists():
        raise ValueError("Use a new destination directory")
    names = {"r1cs": "circuit.r1cs", "wasm": "circuit.wasm", "provingKey": "proving_key.ark", "verificationKey": "verification_key.json"}
    # Validate before copying large files. A mismatch must never create a usable manifest.
    for name in names:
        with Path(manifest["files"][name]).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["sha256"][name]:
                raise ValueError(f"Artifact digest mismatch: {name}")
    witness_dir = Path(manifest["files"]["wasm"]).parent
    destination.mkdir(parents=True, mode=0o700)
    for name, target in names.items():
        shutil.copyfile(manifest["files"][name], destination / target)
        manifest["files"][name] = f"/artifacts/{target}"
    for filename in ("generate_witness.js", "witness_calculator.js"):
        shutil.copyfile(witness_dir / filename, destination / filename)
    manifest["files"]["prover"] = "/usr/local/bin/csi-native-prover"
    manifest["sha256"].pop("prover", None)
    manifest["runtimeProverBinding"] = "Linux binary built from repository Cargo.lock; bound by runtime.py"
    (destination / "artifacts.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export(args.source, args.destination)
    print(f"Portable artifacts exported to {args.destination}; no setup or deployment performed")
