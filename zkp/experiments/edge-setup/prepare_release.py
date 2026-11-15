#!/usr/bin/env python3
"""Audit the existing package and create a separately versioned deployment archive."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent.parent
SOURCE = REPO / "edge/lomb_scargle_e2e"
ARTIFACTS = ROOT / "artifacts"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    changed = []
    count = 0
    for line in (SOURCE / "MANIFEST.sha256").read_text().splitlines():
        expected, name = line.split(None, 1)
        name = name.lstrip("*").removeprefix("./")
        actual = digest(SOURCE / name) if (SOURCE / name).is_file() else "MISSING"
        count += 1
        if actual != expected:
            changed.append(dict(path=name, expected=expected, actual=actual))
    audit = dict(checked_files=count, differences=changed)
    print(json.dumps(audit, indent=2), flush=True)
    if args.audit_only:
        return 1 if changed else 0
    if any(item["path"] != "README.md" for item in changed):
        raise SystemExit("Unexpected executable/key/dependency changes; inspect before releasing")
    destination = ARTIFACTS / "release-20261019" / "lomb_scargle_e2e"
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite {destination}")
    shutil.copytree(SOURCE, destination, symlinks=True,
                    ignore=shutil.ignore_patterns(".DS_Store", "._*", "__pycache__", "*.pyc"))
    # The old README checksum is retained in this explicit release provenance record.
    provenance = dict(release="edge-environment-20261019", source_audit=audit,
                      source_git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
                      modifications="README checksum refreshed in deployment copy only; circuit/key/code unchanged")
    (destination / "DEPLOYMENT_PROVENANCE.json").write_text(json.dumps(provenance, indent=2))
    entries = []
    for path in sorted(destination.rglob("*")):
        relative = path.relative_to(destination).as_posix()
        if path.is_file() and relative != "MANIFEST.sha256":
            entries.append(f"{digest(path)}  ./{relative}")
    (destination / "MANIFEST.sha256").write_text("\n".join(entries) + "\n")
    subprocess.run(["python3", str(destination / "bin/verify_manifest.py")], check=True)
    archive = ARTIFACTS / "csi-lomb-e2e-edge-20261019.tar.gz"
    with tarfile.open(archive, "w:gz", compresslevel=1) as stream:
        stream.add(destination, arcname="lomb_scargle_e2e")
    sha = digest(archive)
    (ARTIFACTS / "csi-lomb-e2e-edge-20261019.tar.gz.sha256").write_text(f"{sha}  {archive.name}\n")
    print(json.dumps(dict(archive=archive.name, bytes=archive.stat().st_size, sha256=sha,
                          manifest_files=len(entries)), indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
