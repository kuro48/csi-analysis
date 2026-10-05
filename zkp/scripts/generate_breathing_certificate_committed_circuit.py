#!/usr/bin/env python3
"""Generate the C1-bound variant without changing the production certificate."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "circuits" / "csi_breathing_certificate.circom"
OUTPUT = ROOT / "circuits" / "csi_breathing_certificate_committed.circom"

DOMAIN_TAG = 0x43534901
FORMAT_VERSION = 1
VALUE_OFFSET = 1 << 10
T = 300


def replace_once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected one generator anchor, found {count}: {old[:80]!r}"
        )
    return source.replace(old, new, 1)


def main() -> None:
    source = SOURCE.read_text()
    source = replace_once(
        source,
        'include "circomlib/circuits/comparators.circom";',
        'include "circomlib/circuits/comparators.circom";\n'
        'include "circomlib/circuits/bitify.circom";\n'
        'include "circomlib/circuits/poseidon.circom";',
    )
    source = replace_once(
        source,
        "template BreathingCertificateCheck(",
        "template BreathingCertificateCommittedCheck(",
    )
    source = replace_once(
        source,
        "    signal input sel[K];\n    signal output isNormal;",
        "    signal input sel[K];\n"
        "    signal input commitmentNonce;\n"
        "    signal input vmdCommitment;\n"
        "    signal output isNormal;",
    )
    commitment_block = f"""
    // ===== C1: canonical Poseidon commitment to vmdInput =====
    component commitmentSeed = Poseidon(3);
    commitmentSeed.inputs[0] <== {DOMAIN_TAG};
    commitmentSeed.inputs[1] <== commitmentNonce;
    commitmentSeed.inputs[2] <== {FORMAT_VERSION};

    component commitmentMetadataLength = Poseidon(2);
    commitmentMetadataLength.inputs[0] <== commitmentSeed.out;
    commitmentMetadataLength.inputs[1] <== {T};
    component commitmentMetadataOffset = Poseidon(2);
    commitmentMetadataOffset.inputs[0] <== commitmentMetadataLength.out;
    commitmentMetadataOffset.inputs[1] <== {VALUE_OFFSET};

    signal encodedVmdInput[T];
    component encodedVmdInputBits[T];
    component commitmentStep[T];
    signal commitmentState[T + 1];
    commitmentState[0] <== commitmentMetadataOffset.out;
    for (var commitmentIndex = 0; commitmentIndex < T; commitmentIndex++) {{
        encodedVmdInput[commitmentIndex] <== vmdInput[commitmentIndex] + {VALUE_OFFSET};
        encodedVmdInputBits[commitmentIndex] = Num2Bits(11);
        encodedVmdInputBits[commitmentIndex].in <== encodedVmdInput[commitmentIndex];
        commitmentStep[commitmentIndex] = Poseidon(2);
        commitmentStep[commitmentIndex].inputs[0] <== commitmentState[commitmentIndex];
        commitmentStep[commitmentIndex].inputs[1] <== encodedVmdInput[commitmentIndex];
        commitmentState[commitmentIndex + 1] <== commitmentStep[commitmentIndex].out;
    }}
    commitmentState[T] === vmdCommitment;

"""
    source = replace_once(
        source,
        "    // ===== 1. sel one-hot 検証 =====",
        commitment_block + "    // ===== 1. sel one-hot 検証 =====",
    )
    source = replace_once(
        source,
        f"component main = BreathingCertificateCheck({T}, 5, 101, 5, 32);",
        f"component main {{public [vmdCommitment]}} = BreathingCertificateCommittedCheck({T}, 5, 101, 5, 32);",
    )
    source = replace_once(source, "証明書検証方式 / 案A", "証明書検証方式 / C1 committed")
    OUTPUT.write_text(source)
    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    main()
