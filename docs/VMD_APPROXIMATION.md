# Circom近似VMD

`csi_vmd_approx.circom` は、PCA後の波形から呼吸帯域のピークを回路内で求める固定反復の近似回路です。VMDの考え方は Dragomiretskiy and Zosso, “Variational Mode Decomposition” の Algorithm 2（[CAM report CAM13-22](https://ww3.math.ucla.edu/camreport/cam13-22.pdf)）を参考にしています。回路では係数と更新則を簡略化しています。

入力は実数の時間領域128サンプル整数波形（`-100..100`）、サンプリング周波数2 Hzです。DFTの実部・虚部は回路内で計算します。正のDFTビン1..63、3モード、初期中心8・24・48を使います。各モードを4回順番に更新し、残差を `residual / (1 + (bin - center)^2)` で重み付けします。整数除算は0方向へ切り捨て、中心はスペクトルエネルギーの重み付き平均の床値とし、エネルギー0なら保持します。

全モードのグローバル最大ピークパワーを比較して選択し、そのピークビンを呼吸推定値とします。ビン7..23を正常帯域とします（2 Hz・128サンプルでは6.5625..21.5625 BPM、ビン間隔0.9375 BPM）。これは離散的な回路判定帯域であり、臨床的な帯域定義そのものではありません。Python側は正常帯域内のピーク比を優先してモードを選ぶため、強度最大ピークを選ぶ本回路とは選択結果も異なり得ます。三角関数表はスケール1000です。有限反復なので収束は保証しません。ラグランジュ乗数の更新は省略（`tau=0`）しており、厳密な再構成は保証しません。VMDで用いるミラー拡張も省略しています。公開出力は `isNormal`、`estimatedFrequencyBin`、`selectedMode0based` だけで、波形・モード係数・中心は公開しません。PCA、サブキャリア選択、前処理の正しさも証明対象外です。

バックエンドはPCA波形を `resample_poly(1, 50)` で約2 Hzにし、64秒（128サンプル）へパディングまたは切り詰めます。Pythonの既存VMDベースラインは5モード・100 Hz前提であり、両者のBPMが一致する保証はありません。

```bash
npm run generate:vmd_approx
npm run compile:vmd_approx
npm run setup:vmd_approx
```

セットアップは既存の `powersOfTau28_hez_final_19.ptau` を使い、Nodeの暗号論的乱数を専用zkeyへの貢献entropyにします。既存証明書用の鍵や固定entropyは再利用しません。
