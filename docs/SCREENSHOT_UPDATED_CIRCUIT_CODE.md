# 変更後の回路コード スクリーンショット用

今回追加した中間ハッシュ処理のコード抜粋です。既存のVMD計算とLomb–Scargle計算は省略し、変更箇所だけを掲載しています。

## VMD近似回路 入出力

```circom
include "circomlib/circuits/poseidon.circom";

template V() {
    // Private inputs
    signal input waveform[128];
    signal input commitmentNonce;

    // Public input: preprocessing projection commitment
    signal input parentCommitment;

    // Public outputs
    signal output isNormal;
    signal output estimatedFrequencyBin;
    signal output selectedMode0based;
    signal output intermediateHash;

    // ... existing VMD approximation constraints ...
}
```

## VMD近似回路 Poseidon中間ハッシュ

```circom
// Domain-separated seed: VMD domain, private nonce, format version
component hashSeed = Poseidon(3);
hashSeed.inputs[0] <== 1129531664; // VMD domain tag
hashSeed.inputs[1] <== commitmentNonce;
hashSeed.inputs[2] <== 1;          // format version

// Bind this proof to the preprocessing proof
component hashParent = Poseidon(2);
hashParent.inputs[0] <== hashSeed.out;
hashParent.inputs[1] <== parentCommitment;

// Bind waveform encoding metadata
component hashLength = Poseidon(2);
hashLength.inputs[0] <== hashParent.out;
hashLength.inputs[1] <== 128;

component hashOffset = Poseidon(2);
hashOffset.inputs[0] <== hashLength.out;
hashOffset.inputs[1] <== 100;

// Bind all private waveform samples
signal hashState[132];
component hashStep[131];
hashState[0] <== hashOffset.out;

for (var ht = 0; ht < 128; ht++) {
    hashStep[ht] = Poseidon(2);
    hashStep[ht].inputs[0] <== hashState[ht];
    hashStep[ht].inputs[1] <== waveform[ht] + 100;
    hashState[ht + 1] <== hashStep[ht].out;
}

// Bind the circuit-derived results
hashStep[128] = Poseidon(2);
hashStep[128].inputs[0] <== hashState[128];
hashStep[128].inputs[1] <== isNormal;
hashState[129] <== hashStep[128].out;

hashStep[129] = Poseidon(2);
hashStep[129].inputs[0] <== hashState[129];
hashStep[129].inputs[1] <== estimatedFrequencyBin;
hashState[130] <== hashStep[129].out;

hashStep[130] = Poseidon(2);
hashStep[130].inputs[0] <== hashState[130];
hashStep[130].inputs[1] <== selectedMode0based;
hashState[131] <== hashStep[130].out;

intermediateHash <== hashState[131];
```

## Lomb–Scargle回路 入出力

```circom
include "circomlib/circuits/poseidon.circom";

template LombScargleFixedPointCheck(
    PCS,
    SAMPLE_COUNT,
    FREQS,
    NORMAL_LOW_BIN,
    NORMAL_HIGH_BIN,
    SAMPLE_OFFSET,
    TRIG_OFFSET,
    INPUT_BITS,
    RATIO_BITS
) {
    // Private inputs
    signal input samples[PCS][SAMPLE_COUNT];
    signal input commitmentNonce;

    // Public inputs
    signal input timestampsMs[SAMPLE_COUNT];
    signal input parentCommitment;

    // Public outputs
    signal output isNormal;
    signal output selectedPc;
    signal output estimatedFrequencyBin;
    signal output globalPeakFrequencyBin;
    signal output intermediateHash;

    // ... existing Lomb–Scargle constraints ...
}
```

## Lomb–Scargle回路 Poseidon中間ハッシュ

```circom
// Domain-separated seed and preprocessing-proof link
component hashSeed = Poseidon(3);
hashSeed.inputs[0] <== 1129531665; // Lomb–Scargle domain tag
hashSeed.inputs[1] <== commitmentNonce;
hashSeed.inputs[2] <== 1;          // format version

component hashParent = Poseidon(2);
hashParent.inputs[0] <== hashSeed.out;
hashParent.inputs[1] <== parentCommitment;

// Bind circuit configuration
signal hashMetadataState[5];
hashMetadataState[0] <== hashParent.out;
var hashMetadata[4] = [PCS, SAMPLE_COUNT, FREQS, SAMPLE_OFFSET];
component hashMetadataStep[4];

for (var metadataIndex = 0; metadataIndex < 4; metadataIndex++) {
    hashMetadataStep[metadataIndex] = Poseidon(2);
    hashMetadataStep[metadataIndex].inputs[0]
        <== hashMetadataState[metadataIndex];
    hashMetadataStep[metadataIndex].inputs[1]
        <== hashMetadata[metadataIndex];
    hashMetadataState[metadataIndex + 1]
        <== hashMetadataStep[metadataIndex].out;
}

// Bind all private PCA samples
signal sampleHashState[PCS * SAMPLE_COUNT + 1];
component sampleHashStep[PCS * SAMPLE_COUNT];
sampleHashState[0] <== hashMetadataState[4];

for (var hashPc = 0; hashPc < PCS; hashPc++) {
    for (var hashSample = 0; hashSample < SAMPLE_COUNT; hashSample++) {
        var samplePosition = hashPc * SAMPLE_COUNT + hashSample;
        sampleHashStep[samplePosition] = Poseidon(2);
        sampleHashStep[samplePosition].inputs[0]
            <== sampleHashState[samplePosition];
        sampleHashStep[samplePosition].inputs[1]
            <== samples[hashPc][hashSample];
        sampleHashState[samplePosition + 1]
            <== sampleHashStep[samplePosition].out;
    }
}

// Bind all public timestamps
signal timestampHashState[SAMPLE_COUNT + 1];
component timestampHashStep[SAMPLE_COUNT];
timestampHashState[0] <== sampleHashState[PCS * SAMPLE_COUNT];

for (var hashTimestamp = 0; hashTimestamp < SAMPLE_COUNT; hashTimestamp++) {
    timestampHashStep[hashTimestamp] = Poseidon(2);
    timestampHashStep[hashTimestamp].inputs[0]
        <== timestampHashState[hashTimestamp];
    timestampHashStep[hashTimestamp].inputs[1]
        <== timestampsMs[hashTimestamp];
    timestampHashState[hashTimestamp + 1]
        <== timestampHashStep[hashTimestamp].out;
}

// Bind all circuit-derived results
signal resultHashState[5];
component resultHashStep[4];
resultHashState[0] <== timestampHashState[SAMPLE_COUNT];

resultHashStep[0] = Poseidon(2);
resultHashStep[0].inputs[0] <== resultHashState[0];
resultHashStep[0].inputs[1] <== isNormal;
resultHashState[1] <== resultHashStep[0].out;

resultHashStep[1] = Poseidon(2);
resultHashStep[1].inputs[0] <== resultHashState[1];
resultHashStep[1].inputs[1] <== selectedPc;
resultHashState[2] <== resultHashStep[1].out;

resultHashStep[2] = Poseidon(2);
resultHashStep[2].inputs[0] <== resultHashState[2];
resultHashStep[2].inputs[1] <== estimatedFrequencyBin;
resultHashState[3] <== resultHashStep[2].out;

resultHashStep[3] = Poseidon(2);
resultHashStep[3].inputs[0] <== resultHashState[3];
resultHashStep[3].inputs[1] <== globalPeakFrequencyBin;
resultHashState[4] <== resultHashStep[3].out;

intermediateHash <== resultHashState[4];
```

## 公開入力による証明チェーン連携

```circom
// VMD: preprocessing commitment is public
component main {public [parentCommitment]} = V();

// Lomb–Scargle: timestamps and preprocessing commitment are public
component main {public [timestampsMs, parentCommitment]}
    = LombScargleFixedPointCheck(
        3,    // PCS
        384,  // SAMPLE_COUNT
        128,  // FREQS
        5,    // NORMAL_LOW_BIN
        54,   // NORMAL_HIGH_BIN
        1024, // SAMPLE_OFFSET
        1024, // TRIG_OFFSET
        11,   // INPUT_BITS
        180   // RATIO_BITS
    );
```

`commitmentNonce` は公開入力リストへ含めないため秘密入力です。`parentCommitment` と `intermediateHash` は公開され、前処理から各解析回路へのコミットメント連続性を検証できます。
