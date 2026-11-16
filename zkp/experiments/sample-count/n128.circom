pragma circom 2.0.0;
include "lomb_scargle_adaptive_samples.circom";
component main {public [timestampsMs, candidateCount]} = LombScargleCSIAdaptiveSamples(128, 4004);
