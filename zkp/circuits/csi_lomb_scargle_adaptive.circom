pragma circom 2.0.0;

include "lomb_scargle_adaptive_core.circom";

// Separate protocol from e2e-v1: 70 public signals, including candidateCount.
// Supply ALL columns; pad missing columns with encoded zero (2048).
// Larger captures require a separately compiled capacity and new keys.
component main {public [timestampsMs, candidateCount]} = LombScargleCSIAdaptive(64);
