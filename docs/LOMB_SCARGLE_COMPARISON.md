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
4. 詳細表示用に、0.05–1.5 Hzの1000点で各PCのLomb–Scargleピリオドグラムを計算する。
5. 6–40 BPM内の最大ピークが最も強いPCを選び、その帯域内ピークを推定BPMとする。
6. 全収録区間を384層に分け、各層から固定seedで1観測点を選ぶ決定論的な
   層化不均一抽出を行い、相対時刻を1 ms単位へ量子化する。
7. Circomが相対時刻から近似sin/cos基底、固定小数点Lomb–Scargleスコアを再計算し、選択PCの
   全探索帯域グローバルピークが6–40 BPM内なら正常とする。

CSI読込からPCAまでは両方式で共有され、Lomb–Scargle側では再実行しない。

帯域内だけで推定ピークを選ぶと推定BPMは必ず6–40 BPMになるため、正常判定には
使わない。正常判定は全探索帯域のグローバルピークに対して行う。

## Circomが証明する範囲

`csi_lomb_scargle_normality.circom` は、3×384点の固定小数点PCA波形を秘密入力、
384点の24-bitミリ秒相対時刻を公開入力として、次を制約する。

- 秘密波形の11-bit入力範囲と公開時刻の24-bit入力範囲
- 象限縮約と入れ子Taylor多項式によるsin/cos近似
- 各周波数binの式から16 binごとにsin/cos基底を再計算し、アンカー間だけ複素回転する128周波数基底の生成
- 各PC・周波数のsin/cos内積
- τを消去した `(SS×C²−2×CS×C×S+CC×S²)/((CC×SS−CS²)×YY)` スコア
- 正常帯域内ピークによるPC選択
- 選択PCの正常帯域内ピークと全帯域グローバルピークの `argmax`
- グローバルピークbinの正常範囲判定

公開出力は `isNormal`、0始まりの選択PC、推定周波数bin、グローバルピークbin。
`isValid` はGroth16証明のローカル検証結果で、`isNormal` とは独立している。

τは近似せず、非直交sin/cos基底のGram行列を使う代数的に等価な式で消去する。
固定小数点の複素回転は16 bin未満に限定し、各アンカーでは公開タイムスタンプと
`frequency(bin) = (127 + 29×bin) / 2540 Hz` からsin/cosを直接再計算する。
これにより、全128 binを連続回転した場合の丸め誤差累積を防ぐ。
三角関数、ピリオドグラム投影、正規化、PC選択、ピーク探索、正常判定は回路内で拘束される。

正確なR1CS制約数と必要なPowers of Tauサイズは `npm run compile:lomb_scargle` の出力を参照する。
Pythonの1000周波数点は詳細表示用、Circomの128周波数点は証明用であるため、量子化により
推定BPMが最大約0.35 BPMずれる場合がある。

## セットアップ

```bash
cd zkp
npm run ptau:fetch24         # 2^24 phase-2 ptau（約19GB）。中断しても再実行でレジューム
npm run generate:lomb_scargle
npm run compile:lomb_scargle
npm run setup:lomb_scargle   # 未取得なら ptau:fetch24 を先に実行する
```

約750万制約（非線形約626万）を収容するには2^24のphase-2 Powers of Tauが必要で、
`keys/powersOfTau28_hez_final_24.ptau`（19,327,446,162バイト）に置く。
既定ではEthereum Foundation Privacy & Scaling ExplorationsのPerpetual Powers of Tau
contribution 0080の、phase-2準備済み `ppot_0080_24.ptau` を取得する。
別の配布元を使う場合は `LOMB_PTAU_URL`、照合サイズを変える場合は `LOMB_PTAU_SIZE` を指定する。
`ptau:generate_dev` / `ptau:generate_dev20` は小さい回路向けのローカル生成用で、
2^24のローカル生成は非現実的なためこの回路では使わない。

Trusted Setupと証明生成はNodeのヒープを既定4GBではなく14GBで実行する。
`ZKP_NODE_MAX_OLD_SPACE_MB` で変更できる。

`ZKP_AUTO_COMPILE=true` のバックエンド起動時にも自動準備される。
