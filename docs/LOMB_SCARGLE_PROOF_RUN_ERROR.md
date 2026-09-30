# Lomb–Scargle Circom 証明生成エラーと解決結果

実行日: 2026-09-23  
対象回路: `csi_lomb_scargle_normality`  
旧回路の制約数: 5,409,149  
新回路の制約数: 7,503,485（非線形 6,261,423、線形 1,242,062）

## 旧回路の実行結果

| 段階 | 結果 |
|---|---|
| R1CS / final zkey 整合性検査 | 成功 (`ZKey Ok!`) |
| witness生成 | **失敗** |
| Groth16 proof生成 | 未実行（witness生成失敗のため） |
| proof verify | 未実行（proof未生成のため） |

## エラー原文

```text
Error: Error: Assert Failed.
Error in template Num2Bits_29 line: 38
Error in template LombRoundSignedTrig_43 line: 60
Error in template LombRotateTrig_44 line: 196
Error in template LombTimestampBasis_45 line: 224
Error in template LombScargleFixedPointCheck_55 line: 52
```

```text
RuntimeError: [Lomb_scargle_normality] Witness generation failed: returncode=1
```

## エラーの内容

公開タイムスタンプから128周波数分のsin/cos基底を生成する際、
周波数方向の複素回転を繰り返すことで固定小数点値に丸め誤差が蓄積する。
その値が `LombRoundSignedTrig` の11-bit範囲（0〜2047）を外れ、
`Num2Bits(11)` の制約に違反したためwitnessを生成できない。

独自の不均一時刻入力だけでなく、
`zkp/test/lomb_scargle_core.test.js` に記載された既存テストと完全に同じ入力でも再現した。
したがって、入力データ固有ではなく、現在の回路またはコンパイル成果物の構造的な問題である。

同じ整数演算を回路外で再現したところ、周波数方向の連続回転後の符号化値は
期待範囲 `0..2047` に対して最小 `-64`、最大 `2117` になった。
最初の範囲違反は周波数bin 98のcos値 `-3` だった。

## 対処方針

推奨対応は、全128周波数を直前のbinから連続回転して生成せず、
一定間隔（例: 16 bin）ごとに公開タイムスタンプからsin/cosを直接再計算することである。
各アンカー間だけ複素回転を使えば、丸め誤差の累積を抑えつつ制約数の増加も限定できる。

単純に `Num2Bits(11)` を12-bitへ広げるだけでは、負値 `-64` を表現できないため解決しない。
符号化オフセットを1024から2048へ変更し、12-bit化する方法は応急処置として可能だが、
全24-bitタイムスタンプ範囲における上下限と比較回路のbit幅を改めて検証する必要がある。

現行ソースを使う `npm test -- --grep 'dominant frequency'` も実行したが、
大規模回路のテスト用再コンパイルがMochaの600秒timeoutを超え、witness検査前に終了した。
テストtimeoutも回路規模に合わせて延長する必要がある。

## 解決結果（2026-09-24）

16 binごとにタイムスタンプからsin/cos基底を直接再計算し、アンカー間だけ最大15回の
複素回転を行う回路へ変更した。これにより連続127回転の丸め誤差蓄積を解消した。

| 段階 | 結果 |
|---|---|
| Circomコンパイル | 成功（7,503,485制約） |
| Trusted Setup | 成功 |
| contribution | 成功 |
| verification key生成 | 成功 |
| witness生成 | 成功（10.990秒） |
| Groth16 proof生成 | 成功（985.948秒） |
| proof verify | 成功（3.960秒、`isValid=true`） |

0.25 Hzの不規則サンプリング入力に対し、回路出力はbin 18、
0.255511811 Hz（15.3307087 BPM）だった。Python側の真値15 BPMとの差は
128-bin周波数グリッドの量子化範囲内である。

最初のend-to-end実行ではproof生成後、サービス実装のverify固定10秒timeoutにより
次のエラーも発生した。

```text
subprocess.TimeoutExpired: Command '['npx', 'snarkjs', 'groth16', 'verify', ...]
timed out after 10 seconds
```

これはproof不正ではなく起動時間を含む制限値の問題だったため、グローバル`snarkjs`を
優先して直接起動し、timeoutを60秒に変更した。再実行ではverifyが3.960秒で成功した。

## 旧時点の結論

回路のコンパイルとTrusted Setupは完了しており、R1CSとfinal zkeyも整合している。
しかし、現状はwitness生成を完走できないため、Lomb–Scargle回路のGroth16証明は生成・検証できない。
