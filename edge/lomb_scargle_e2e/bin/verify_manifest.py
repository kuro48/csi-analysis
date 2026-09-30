#!/usr/bin/env python3
"""Verify every packaged file without printing one line per dependency."""

import hashlib
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    manifest = root / "MANIFEST.sha256"
    checked = 0
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(None, 1)
        relative = relative.lstrip("*").removeprefix("./")
        path = root / relative
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise SystemExit(f"checksum mismatch: {relative}")
        checked += 1
    print(f"manifest OK: {checked} files")


if __name__ == "__main__":
    main()
