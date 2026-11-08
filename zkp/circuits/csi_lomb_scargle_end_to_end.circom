pragma circom 2.0.0;

include "lomb_scargle_csi_core.circom";

// Feasibility-sized end-to-end circuit:
// - 64 irregular samples
// - 8 private CSI subcarriers
// - 32 frequency bins from 0.05 through approximately 0.404 Hz
// - normal bins 5..27 = approximately 6.43 through 21.50 BPM
//
// RATIO_BITS=236 follows a conservative integer bound for 12-bit I/Q,
// 64 samples, 11-bit trigonometric values, and cross-multiplied scores.
component main {public [timestampsMs]} = LombScargleCSIEndToEnd(
    64,
    8,
    32,
    5,
    27,
    23,
    2048,
    12,
    1024,
    236
);
