pragma circom 2.0.0;

include "../node_modules/circomlib/circuits/comparators.circom";

template SampleBreathing() {
    signal input breathingRate;

    signal output isValid;  // 1 = 正常範囲内, 0 = 範囲外

    component minCheck = GreaterEqThan(8);
    minCheck.in[0] <== breathingRate;
    minCheck.in[1] <== 10;  // 最小閾値

    component maxCheck = LessEqThan(8);
    maxCheck.in[0] <== breathingRate;
    maxCheck.in[1] <== 30;  // 最大閾値

    isValid <== minCheck.out * maxCheck.out;
}

component main = SampleBreathing();
