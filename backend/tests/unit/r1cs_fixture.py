"""テスト用の最小 `.r1cs` バイナリ生成ヘルパー。"""

import struct

from app.services.zkp_circuit_metrics import R1CS_MAGIC

BN254_PRIME = 21888242871839275222246405745257275088548364400416034343698204186575808495617


def build_r1cs_bytes(
    constraint_count: int = 11354,
    wire_count: int = 13049,
    public_output_count: int = 1,
    public_input_count: int = 0,
    private_input_count: int = 1805,
    label_count: int = 14169,
    leading_section: bool = False,
) -> bytes:
    """iden3 R1CS 仕様のヘッダだけを持つ最小ファイルを組み立てる。"""
    prime = BN254_PRIME.to_bytes(32, "little")
    header_body = (
        struct.pack("<I", len(prime))
        + prime
        + struct.pack("<IIII", wire_count, public_output_count, public_input_count, private_input_count)
        + struct.pack("<Q", label_count)
        + struct.pack("<I", constraint_count)
    )

    sections = b""
    section_count = 1
    if leading_section:
        # ヘッダより前に別セクションが来ても読み飛ばせることを確認するための詰め物
        filler = b"\x00" * 24
        sections += struct.pack("<IQ", 2, len(filler)) + filler
        section_count += 1
    sections += struct.pack("<IQ", 1, len(header_body)) + header_body

    return R1CS_MAGIC + struct.pack("<II", 1, section_count) + sections
