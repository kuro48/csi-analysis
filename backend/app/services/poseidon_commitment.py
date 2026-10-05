"""Canonical commitments shared by the Python and Circom pipeline stages."""

import json
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

COMMITMENT_FORMAT_VERSION = 1
VMD_INPUT_DOMAIN_TAG = 0x43534901
RAW_CSI_DOMAIN_TAG = 0x43534900
VMD_VALUE_OFFSET = 1 << 10
RAW_CSI_VALUE_OFFSET = 1 << 31
RAW_CSI_SCALE = 1_000
PREPROCESS_INPUT_DOMAIN_TAG = 0x43534902
PREPROCESS_OUTPUT_DOMAIN_TAG = 0x43534903


@dataclass(frozen=True)
class Commitment:
    value: str
    nonce: str
    domain_tag: int
    version: int
    value_count: int
    metadata: tuple[int, ...]

    def as_dict(self, *, include_nonce: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "value": self.value,
            "domain_tag": self.domain_tag,
            "version": self.version,
            "value_count": self.value_count,
            "metadata": list(self.metadata),
        }
        if include_nonce:
            result["nonce"] = self.nonce
        return result


def new_commitment_nonce() -> int:
    """Return a non-zero 128-bit salt that fits safely in the BN254 field."""

    return secrets.randbits(128) or 1


def _commit(
    *,
    domain_tag: int,
    nonce: int,
    metadata: Sequence[int],
    values: Iterable[int],
    zkp_dir: str | None = None,
) -> Commitment:
    normalized_values = [int(value) for value in values]
    normalized_metadata = tuple(int(value) for value in metadata)
    root = Path(zkp_dir) if zkp_dir else Path(__file__).resolve().parents[3] / "zkp"
    script = root / "scripts" / "poseidon_commit.js"
    if not script.is_file():
        raise FileNotFoundError(f"Poseidon helper not found: {script}")

    request = {
        "domainTag": str(domain_tag),
        "nonce": str(nonce),
        "version": str(COMMITMENT_FORMAT_VERSION),
        "metadata": [str(value) for value in normalized_metadata],
        "values": [str(value) for value in normalized_values],
    }
    completed = subprocess.run(
        ["node", str(script)],
        cwd=root,
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Poseidon commitment failed: {completed.stderr.strip()}")
    value = str(json.loads(completed.stdout)["commitment"])
    return Commitment(
        value=value,
        nonce=str(nonce),
        domain_tag=domain_tag,
        version=COMMITMENT_FORMAT_VERSION,
        value_count=len(normalized_values),
        metadata=normalized_metadata,
    )


def commit_vmd_input(values: Sequence[int], nonce: int, zkp_dir: str | None = None) -> Commitment:
    """Commit to a fixed-order signed VMD input using offset encoding."""

    signed = [int(value) for value in values]
    encoded = [value + VMD_VALUE_OFFSET for value in signed]
    if any(value < 0 or value >= 2 * VMD_VALUE_OFFSET for value in encoded):
        raise ValueError(f"VMD input must be in [-{VMD_VALUE_OFFSET}, {VMD_VALUE_OFFSET - 1}]")
    return _commit(
        domain_tag=VMD_INPUT_DOMAIN_TAG,
        nonce=nonce,
        metadata=(len(encoded), VMD_VALUE_OFFSET),
        values=encoded,
        zkp_dir=zkp_dir,
    )


def commit_raw_csi(
    matrix: np.ndarray,
    nonce: int,
    *,
    scale: int = RAW_CSI_SCALE,
    zkp_dir: str | None = None,
) -> Commitment:
    """Commit complex CSI in sample-major, subcarrier-major, interleaved I/Q order."""

    csi = np.asarray(matrix, dtype=np.complex128)
    if csi.ndim != 2 or csi.size == 0 or not np.all(np.isfinite(csi)):
        raise ValueError("CSI matrix must be a finite, non-empty two-dimensional array")
    quantized_i = np.rint(csi.real * scale).astype(object)
    quantized_q = np.rint(csi.imag * scale).astype(object)
    encoded: list[int] = []
    for row in range(csi.shape[0]):
        for column in range(csi.shape[1]):
            for signed in (int(quantized_i[row, column]), int(quantized_q[row, column])):
                value = signed + RAW_CSI_VALUE_OFFSET
                if value < 0 or value >= 2 * RAW_CSI_VALUE_OFFSET:
                    raise ValueError("Quantized CSI component exceeds signed 32-bit commitment range")
                encoded.append(value)
    return _commit(
        domain_tag=RAW_CSI_DOMAIN_TAG,
        nonce=nonce,
        metadata=(csi.shape[0], csi.shape[1], scale, RAW_CSI_VALUE_OFFSET),
        values=encoded,
        zkp_dir=zkp_dir,
    )


def commit_preprocess_input(
    centered_matrix: Sequence[Sequence[int]],
    weights: Sequence[int],
    nonce: int,
    zkp_dir: str | None = None,
) -> Commitment:
    rows = [[int(value) for value in row] for row in centered_matrix]
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("centered_matrix must be a non-empty rectangular matrix")
    if len(weights) != len(rows[0]):
        raise ValueError("weights length must equal the matrix column count")
    values = [value + 128 for row in rows for value in row] + [int(value) + 128 for value in weights]
    if any(value < 0 or value >= 256 for value in values):
        raise ValueError("preprocess matrix and weights must be in [-128, 127]")
    return _commit(
        domain_tag=PREPROCESS_INPUT_DOMAIN_TAG,
        nonce=nonce,
        metadata=(len(rows), len(rows[0]), 128, 128),
        values=values,
        zkp_dir=zkp_dir,
    )


def commit_preprocess_projection(projected: Sequence[int], nonce: int, zkp_dir: str | None = None) -> Commitment:
    offset = 1 << 17
    encoded = [int(value) + offset for value in projected]
    if any(value < 0 or value >= 2 * offset for value in encoded):
        raise ValueError("projected values exceed the signed 18-bit range")
    return _commit(
        domain_tag=PREPROCESS_OUTPUT_DOMAIN_TAG,
        nonce=nonce,
        metadata=(len(encoded), offset),
        values=encoded,
        zkp_dir=zkp_dir,
    )
