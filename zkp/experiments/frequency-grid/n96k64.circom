pragma circom 2.0.0;
include "lomb_scargle_adaptive_grid.circom";
component main {public [timestampsMs, candidateCount]} = LombScargleCSIAdaptiveGrid(96, 4004, 64);
