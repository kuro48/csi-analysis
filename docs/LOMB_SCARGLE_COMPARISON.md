# Lomb–Scargle比較アルゴリズム

`lomb-scargle.ipynb` を基に、不均一なPicoScenes `systemns` タイムスタンプを
補間せずに使う呼吸数推定を実装した。既存の `5-1.ipynb` 方式と同じ
`POST /api/v2/breathing/analyze-verifiable` で両方式を実行し、推定値とCircom判定を
同じレスポンスで比較できる。

## 処理

1. 取得・アップロードされたCSIと、同じフレームの `systemns` を同期して一度だけ読み込む。
2. 既存の5-1パイプラインで、振幅化、FFT/SNRによる上位256サブキャリア選択、
   バンドパス、時間領域PCA（3成分）までを実行する。
3. 既存処理が生成したPCA出力とタイムスタンプを、行の対応を保ったまま時刻順に整列し、
   重複時刻を除く。
4. 0.05–1.5 Hzの1000点で各PCのLomb–Scargleピリオドグラムを計算する。
5. 6–40 BPM内の最大ピークが最も強いPCを選び、その帯域内ピークを推定BPMとする。
6. 選択PCの全探索帯域グローバルピークをCircomで求め、6–40 BPM内なら正常とする。

CSI読込からPCAまでは両方式で共有され、Lomb–Scargle側では再実行しない。

帯域内だけで推定ピークを選ぶと推定BPMは必ず6–40 BPMになるため、正常判定には
使わない。正常判定は全探索帯域のグローバルピークに対して行う。

## Circomが証明する範囲

`csi_lomb_scargle_normality.circom` は、Pythonが0–1,000,000へ量子化した
3×1000点のピリオドグラムを秘密入力として、次を制約する。

- 全パワー値の範囲
- 正常帯域内ピークによるPC選択
- 選択PCの正常帯域内ピークと全帯域グローバルピークの `argmax`
- グローバルピークbinの正常範囲判定

公開出力は `isNormal`、0始まりの選択PC、推定周波数bin、グローバルピークbin。
`isValid` はGroth16証明のローカル検証結果で、`isNormal` とは独立している。

不均一時刻に対する三角関数・浮動小数点Lomb–Scargle変換そのものは回路外である。
したがって、この証明は「与えられたピリオドグラムの選択・ピーク・判定が正しい」
ことを保証する証明書であり、生CSIからピリオドグラムまでの完全性は保証しない。

## セットアップ

```bash
cd zkp
npm run generate:lomb_scargle
npm run compile:lomb_scargle
npm run setup:lomb_scargle
```

`ZKP_AUTO_COMPILE=true` のバックエンド起動時にも自動準備される。
