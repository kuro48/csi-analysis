# 各比較proofの中間publicによるLomb–Scargle再測定

この系列では1/2/4/8/16/32本の**全比較回路**へ同じ中間public出力を追加する。図の値は、その比較行の新しいproofが検証した `public.json` からのみデコードする。別の診断実行のproof/public/trace、古い鍵やWASM/R1CSは利用しない。I/Q、振幅二乗、中心化波形、三角関数基底、射影、正規化スコアの分子・分母、各SCピークが公開される研究用の比較方式である。

## データ・反復

- Raw8件、各先頭48秒。同一Tx0/Rx0、入れ子tone選択、同じ64時刻とms丸め、32候補共通スケール。
- 入力JSONは従来の通常比較から**nonceを含めbyte-identical**で保存。新しい公開中間回路・新しいsetup/鍵・新しいproofを使う。
- 各構成につき8窓を各1proof、`csi_20260526_034004_w0` のみ追加2proof。計10proof/config、代表入力だけ3反復。
- 代表3回の中央値と8入力横断の平均は別項目。追加repeatをn=8の平均へ混ぜない。
- 古い通常回路の時間計測代表は114943であり、今回の034004との時間倍率比較はしない。
- 正解呼吸数ラベルは無いため、生体的な精度は主張しない。推定4出力は旧 `lomb/accuracy.csv` の同じwindow/SC条件と照合する。

## 証拠とviewer

`plan.json` はキャンペーンと60runの固定計画、`index.json` は表示候補一覧。各 `runs/<run_id>/manifest.json` が唯一の比較行の入口となる。pathはこのlombディレクトリからの相対パス。

成功表示の条件は `status=verified`、`verified=true` と、source/input/schema/R1CS/WASM/vkey/proof/public/decoded/traceのSHA-256一致。`decoded_from` は当該 `artifacts.public` と一致する。`decoded_public.json` と `trace.json` のprovenanceには同じrun_id・config・window・repeat・元artifactのpath/hashが入る。未完了runの図を表示してはならない。

schemaは当該Circom `.sym` のpublic witness番号およびR1CS headerのnOutputs/nPublicInputsと照合する。proofの `public.json` は当該入力から計算したwitness public prefixとも一致確認する。

各runでGroth16 verify、旧4出力との一致、独立整数参照に対する全中間値の検算、中間public1値改ざんによるverify拒否を確認する。整数参照は**検算専用**で、図の値を置き換えない。trace内の中心化/64および分子/分母の浮動比は表示用変換と明記する。

## 実行

準備だけ（重い処理なし）:

```sh
OPENBLAS_NUM_THREADS=1 python3 zkp/experiments/2026-10-26/remeasure_public/lomb/run.py --prepare
```

CPU専有を確認してから、小型3構成を逐次実行:

```sh
OPENBLAS_NUM_THREADS=1 python3 zkp/experiments/2026-10-26/remeasure_public/lomb/run.py --execute --counts 1,2,4 --heap-mib 8192 --prune-key
```

1構成の実行はcompile、schema照合、新setup、乱数contribution、10proof/verify・検算の順。`--prune-key` は10件すべて成功した構成の巨大proving keyだけを削除する。公開verification key、proof/public、R1CS/WASMとhashは保持する。witnessは各runのSHAを記録して証明成功後削除する。

## 計時と資源限界

`configs/sc*/status.json` にcompile/setup/contribution時間、制約数、public数、失敗stage/statusを保存する。`runs_summary.json` は全個票、`config_summary.json` は代表3回とRaw8件の別集計。witness時間はNode起動・WASM読込・ファイル書込込みであり、旧系列の内部WASM-only時間と同一指標ではない。prove/verifyもプロセス起動込み。

公開数は `4293 + 387×SC`（タイムスタンプ64個込み）。追加制約は過去の8本回路の実測差から約64×SCを予測するが、新規コンパイルが確定値を出すまでは未測定。capacityは制約数だけでなく公開信号数も加えた上限でチェックする。

通常32本には8GiB heapでsetup OOM、12GiB heapでsetup1800秒timeoutの既往がある。今回の32本も成功を保証しない。setup/proveのtimeout・OOMは構成statusと各未完了runに残し、未実施時間を成功値として扱わない。失敗したpartial initial.zkeyは無効として削除する。昼の報告はまず小型の実測成功分を優先する。

## 小型3構成の完了結果

SC1/2/4は各10proof、計30proofでverify・中間値検算・tamper拒否に成功。代表034004のprove中央値は4.8688 / 5.0361 / 5.6315秒。Raw8件の平均は別集計で5.0368 / 5.3510 / 5.6762秒。SC8/16/32はこの時点では未実行。

代表の3反復は入力とnonceが同じためpublic statement/hashが一致するが、新しく生成したproof hashとrun_idはそれぞれ異なる。`small_validation.json` は30個の一意なproofと24個の一意なpublic statement、および当該runへのtrace/decodedの結び付きを確認した記録。
