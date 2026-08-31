"""Circom 回路の静的メトリクス（制約数など）を .r1cs ヘッダから読み取る。

snarkjs を起動せずに済むよう、iden3 の R1CS バイナリ仕様に従って
ヘッダセクションだけを直接パースする。数十MBの .r1cs でも読むのは
先頭の数十バイトのみ。
"""

import logging
import os
import struct
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Dict, Optional, Union

logger = logging.getLogger(__name__)

R1CS_MAGIC = b"r1cs"
HEADER_SECTION_TYPE = 1

# 壊れたファイルでセクション走査が暴走しないための上限
MAX_SECTION_SCAN = 64
SECTION_HEADER_BYTES = 12


def read_r1cs_metrics(r1cs_path: Union[Path, str]) -> Optional[Dict[str, int]]:
    """.r1cs から制約数・ワイヤ数などを読む。読めない場合は None を返す。

    回路メトリクスは計測用の付加情報であり、証明生成を止めてはいけないため、
    例外は送出せず None に畳む。
    """
    path = Path(r1cs_path)
    try:
        stat = path.stat()
    except OSError:
        return None

    cached = _read_cached(str(path), stat.st_mtime_ns, stat.st_size)
    return dict(cached) if cached is not None else None


@lru_cache(maxsize=32)
def _read_cached(path_str: str, mtime_ns: int, size: int) -> Optional[Dict[str, int]]:
    """(パス, 更新時刻, サイズ) が同じ間はパース結果を再利用する。"""
    try:
        with open(path_str, "rb") as stream:
            return _parse_metrics(stream)
    except (OSError, ValueError, struct.error) as exc:
        logger.warning("Failed to read r1cs metrics from %s: %s", path_str, exc)
        return None


def _parse_metrics(stream: BinaryIO) -> Dict[str, int]:
    magic = stream.read(4)
    if magic != R1CS_MAGIC:
        raise ValueError(f"r1cs magic mismatch: {magic!r}")

    _version, section_count = struct.unpack("<II", _read_exactly(stream, 8))

    for _ in range(min(section_count, MAX_SECTION_SCAN)):
        section_type, section_size = struct.unpack("<IQ", _read_exactly(stream, SECTION_HEADER_BYTES))
        if section_type == HEADER_SECTION_TYPE:
            return _parse_header_section(stream)
        stream.seek(section_size, os.SEEK_CUR)

    raise ValueError("r1cs header section not found")


def _parse_header_section(stream: BinaryIO) -> Dict[str, int]:
    (field_size,) = struct.unpack("<I", _read_exactly(stream, 4))
    stream.seek(field_size, os.SEEK_CUR)  # 素数フィールドは使わない

    wire_count, public_output_count, public_input_count, private_input_count = struct.unpack(
        "<IIII", _read_exactly(stream, 16)
    )
    (label_count,) = struct.unpack("<Q", _read_exactly(stream, 8))
    (constraint_count,) = struct.unpack("<I", _read_exactly(stream, 4))

    return {
        "constraint_count": constraint_count,
        "wire_count": wire_count,
        "public_output_count": public_output_count,
        "public_input_count": public_input_count,
        "private_input_count": private_input_count,
        "label_count": label_count,
    }


def _read_exactly(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise ValueError(f"truncated r1cs: expected {size} bytes, got {len(data)}")
    return data
