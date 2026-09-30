pragma circom 2.0.0;

include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";

// Integer div/mod. Both quotient and remainder are range constrained so this
// cannot degrade into finite-field division.
template LombDivMod(DIVISOR, Q_BITS, R_BITS) {
    signal input numerator;
    signal output quotient;
    signal output remainder;
    quotient <-- numerator \ DIVISOR;
    remainder <-- numerator % DIVISOR;
    numerator === quotient * DIVISOR + remainder;
    component qb = Num2Bits(Q_BITS);
    component rb = Num2Bits(R_BITS);
    component rlt = LessThan(R_BITS);
    qb.in <== quotient;
    rb.in <== remainder;
    rlt.in[0] <== remainder;
    rlt.in[1] <== DIVISOR;
    rlt.out === 1;
}

template LombRoundUnsigned(DIVISOR, Q_BITS, R_BITS) {
    signal input numerator;
    signal output quotient;
    signal shifted;
    signal remainder;
    shifted <== numerator + DIVISOR \ 2;
    quotient <-- shifted \ DIVISOR;
    remainder <-- shifted % DIVISOR;
    shifted === quotient * DIVISOR + remainder;
    component qb = Num2Bits(Q_BITS);
    component rb = Num2Bits(R_BITS);
    component rlt = LessThan(R_BITS);
    qb.in <== quotient;
    rb.in <== remainder;
    rlt.in[0] <== remainder;
    rlt.in[1] <== DIVISOR;
    rlt.out === 1;
}

// Round a signed fixed-point product by shifting it into the non-negative
// domain. encoded is round(numerator/1000)+1024.
template LombRoundSignedTrig() {
    signal input numerator;
    signal output encoded;
    signal shifted;
    signal quotient;
    signal remainder;
    shifted <== numerator + 4096500;
    quotient <-- shifted \ 1000;
    remainder <-- shifted % 1000;
    shifted === quotient * 1000 + remainder;
    encoded <== quotient - 3072;
    component eb = Num2Bits(11);
    component rb = Num2Bits(10);
    component rlt = LessThan(10);
    eb.in <== encoded;
    rb.in <== remainder;
    rlt.in[0] <== remainder;
    rlt.in[1] <== 1000;
    rlt.out === 1;
}

/*
 * Approximate sin/cos for a cycle position.
 * After quadrant reduction, x is in [0,pi/2] at scale 10000 and y=x^2.
 *   sin(x) ~= x(1-y/6(1-y/20(1-y/42(1-y/72))))
 *   cos(x) ~= 1-y/2(1-y/12(1-y/30(1-y/56)))
 */
template LombApproxSinCos(PERIOD, CYCLE_MULTIPLIER, R_BITS) {
    signal input timeMs;
    signal output sinEncoded;
    signal output cosEncoded;
    signal phaseNumerator;
    phaseNumerator <== timeMs * CYCLE_MULTIPLIER;
    component cycle = LombDivMod(PERIOD, 16, R_BITS);
    cycle.numerator <== phaseNumerator;

    signal fourR;
    signal quadrant;
    signal local;
    fourR <== 4 * cycle.remainder;
    quadrant <-- fourR \ PERIOD;
    local <-- fourR % PERIOD;
    fourR === quadrant * PERIOD + local;
    component qbits = Num2Bits(2);
    component lbits = Num2Bits(R_BITS);
    component llt = LessThan(R_BITS);
    qbits.in <== quadrant;
    lbits.in <== local;
    llt.in[0] <== local;
    llt.in[1] <== PERIOD;
    llt.out === 1;

    signal angleNumerator;
    angleNumerator <== local * 15708;
    component angle = LombRoundUnsigned(PERIOD, 15, R_BITS);
    angle.numerator <== angleNumerator;
    signal square;
    square <== angle.quotient * angle.quotient;
    component y = LombRoundUnsigned(10000, 16, 14);
    y.numerator <== square;

    component s72 = LombRoundUnsigned(720000, 16, 20);
    component s42 = LombRoundUnsigned(420000, 16, 19);
    component s20 = LombRoundUnsigned(200000, 16, 18);
    component s6 = LombRoundUnsigned(60000, 16, 16);
    component sf = LombRoundUnsigned(10000, 15, 14);
    signal sh72;
    signal sh42;
    signal sh20;
    signal sh6;
    s72.numerator <== y.quotient * 10000;
    sh72 <== 10000 - s72.quotient;
    s42.numerator <== y.quotient * sh72;
    sh42 <== 10000 - s42.quotient;
    s20.numerator <== y.quotient * sh42;
    sh20 <== 10000 - s20.quotient;
    s6.numerator <== y.quotient * sh20;
    sh6 <== 10000 - s6.quotient;
    sf.numerator <== angle.quotient * sh6;

    component c56 = LombRoundUnsigned(560000, 16, 20);
    component c30 = LombRoundUnsigned(300000, 16, 19);
    component c12 = LombRoundUnsigned(120000, 16, 17);
    component c2 = LombRoundUnsigned(20000, 16, 15);
    signal ch56;
    signal ch30;
    signal ch12;
    signal cf;
    c56.numerator <== y.quotient * 10000;
    ch56 <== 10000 - c56.quotient;
    c30.numerator <== y.quotient * ch56;
    ch30 <== 10000 - c30.quotient;
    c12.numerator <== y.quotient * ch30;
    ch12 <== 10000 - c12.quotient;
    c2.numerator <== y.quotient * ch12;
    cf <== 10000 - c2.quotient;

    component sm = LombRoundUnsigned(10, 11, 4);
    component cm = LombRoundUnsigned(10, 11, 4);
    sm.numerator <== sf.quotient;
    cm.numerator <== cf;
    signal q0;
    signal q1;
    signal q2;
    signal q3;
    signal sinQ0;
    signal sinQ1;
    signal sinQ2;
    signal sinQ3;
    signal cosQ0;
    signal cosQ1;
    signal cosQ2;
    signal cosQ3;
    q0 <== (1-qbits.out[1]) * (1-qbits.out[0]);
    q1 <== (1-qbits.out[1]) * qbits.out[0];
    q2 <== qbits.out[1] * (1-qbits.out[0]);
    q3 <== qbits.out[1] * qbits.out[0];
    sinQ0 <== q0 * sm.quotient;
    sinQ1 <== q1 * cm.quotient;
    sinQ2 <== q2 * sm.quotient;
    sinQ3 <== q3 * cm.quotient;
    cosQ0 <== q0 * cm.quotient;
    cosQ1 <== q1 * sm.quotient;
    cosQ2 <== q2 * cm.quotient;
    cosQ3 <== q3 * sm.quotient;
    sinEncoded <== 1024 + sinQ0 + sinQ1 - sinQ2 - sinQ3;
    cosEncoded <== 1024 + cosQ0 - cosQ1 - cosQ2 + cosQ3;
}

template LombRotateTrig() {
    signal input cosCurrent;
    signal input sinCurrent;
    signal input cosStep;
    signal input sinStep;
    signal output cosNext;
    signal output sinNext;
    signal cn;
    signal sn;
    signal cc;
    signal ss;
    signal sc;
    signal cs;
    cc <== (cosCurrent-1024)*(cosStep-1024);
    ss <== (sinCurrent-1024)*(sinStep-1024);
    sc <== (sinCurrent-1024)*(cosStep-1024);
    cs <== (cosCurrent-1024)*(sinStep-1024);
    cn <== cc - ss;
    sn <== sc + cs;
    component rc = LombRoundSignedTrig();
    component rs = LombRoundSignedTrig();
    rc.numerator <== cn;
    rs.numerator <== sn;
    cosNext <== rc.encoded;
    sinNext <== rs.encoded;
}

// frequency(bin) = 0.05 + bin * 29/2540 Hz
//                = (127 + 29*bin) / 2540 Hz.
//
// A long fixed-point rotation chain accumulates enough rounding error to move
// encoded sin/cos outside 11 bits. Re-anchor directly from the timestamp every
// ANCHOR_INTERVAL bins and rotate only within each short block. This preserves
// the compact circuit while preventing error propagation across all 128 bins.
template LombTimestampBasis(SAMPLES, FREQS, ANCHOR_INTERVAL) {
    signal input timestampsMs[SAMPLES];
    signal output cosBasis[FREQS][SAMPLES];
    signal output sinBasis[FREQS][SAMPLES];

    component step[SAMPLES];
    for (var i=0; i<SAMPLES; i++) {
        step[i] = LombApproxSinCos(2540000, 29, 22);
        step[i].timeMs <== timestampsMs[i];
    }

    var ANCHORS = (FREQS + ANCHOR_INTERVAL - 1) \ ANCHOR_INTERVAL;
    component anchors[ANCHORS][SAMPLES];
    component rotations[FREQS-ANCHORS][SAMPLES];
    var rotationIndex = 0;
    for (var f=0; f<FREQS; f++) {
        for (var i=0; i<SAMPLES; i++) {
            if (f % ANCHOR_INTERVAL == 0) {
                anchors[f \ ANCHOR_INTERVAL][i] = LombApproxSinCos(2540000, 127 + 29*f, 22);
                anchors[f \ ANCHOR_INTERVAL][i].timeMs <== timestampsMs[i];
                cosBasis[f][i] <== anchors[f \ ANCHOR_INTERVAL][i].cosEncoded;
                sinBasis[f][i] <== anchors[f \ ANCHOR_INTERVAL][i].sinEncoded;
            } else {
                rotations[rotationIndex][i] = LombRotateTrig();
                rotations[rotationIndex][i].cosCurrent <== cosBasis[f-1][i];
                rotations[rotationIndex][i].sinCurrent <== sinBasis[f-1][i];
                rotations[rotationIndex][i].cosStep <== step[i].cosEncoded;
                rotations[rotationIndex][i].sinStep <== step[i].sinEncoded;
                cosBasis[f][i] <== rotations[rotationIndex][i].cosNext;
                sinBasis[f][i] <== rotations[rotationIndex][i].sinNext;
            }
        }
        if (f % ANCHOR_INTERVAL != 0) {
            rotationIndex++;
        }
    }
}
