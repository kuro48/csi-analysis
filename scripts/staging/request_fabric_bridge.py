#!/usr/bin/env python3
"""Call a bridge with host-local credentials; print only its response and elapsed time."""

import argparse
import json
import ssl
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def request_bridge(url: str, token_file: Path, ca_file: Path, payload: Path | None = None) -> dict:
    if urlparse(url).scheme != "https":
        raise ValueError("This staging client requires HTTPS")
    token = token_file.read_text().strip()
    if len(token) < 32:
        raise ValueError("Invalid bridge token")
    request = Request(
        url,
        data=payload.read_bytes() if payload else None,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    context = ssl.create_default_context(cafile=str(ca_file))
    started = time.perf_counter()
    try:
        with urlopen(request, context=context, timeout=150) as response:
            status, result = response.status, json.load(response)
    except HTTPError as error:
        status, result = error.code, json.load(error)
    return {"httpStatus": status, "httpElapsedMs": (time.perf_counter() - started) * 1000, "response": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--ca-file", type=Path, required=True)
    parser.add_argument("--payload", type=Path)
    args = parser.parse_args()
    reply = request_bridge(args.url, args.token_file, args.ca_file, args.payload)
    print(json.dumps(reply, indent=2))
    raise SystemExit(0 if reply["httpStatus"] == 200 else 1)
