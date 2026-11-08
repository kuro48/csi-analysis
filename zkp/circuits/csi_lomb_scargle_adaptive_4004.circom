pragma circom 2.0.0;

include "lomb_scargle_adaptive_core.circom";

// Full 1001-tone x 2-Rx x 2-Tx input pool, without external ranking.
component main {public [timestampsMs, candidateCount]} = LombScargleCSIAdaptive(4004);
