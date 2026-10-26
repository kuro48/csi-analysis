# Lomb–Scargle サブキャリア数比較（2026-10-26）

## 主結果（Raw実データのみ）

8件×6本数の48条件で実WASM出力が整数参照と一致し、同条件の浮動LSとも推定bin・選択SCが一致した。1/2/4/8/16本は各3回、計15証明を生成し全てverify成功。32本はwitness評価成功だが、鍵setupがメモリ上限・時間上限に達し、proof未実施。

| 物理SC数 | 制約数 | witness平均 秒（8窓） | prove中央値 秒（3回） | 全tone基準との差 BPM |
|---:|---:|---:|---:|---:|
| 1 | 311,002 | 0.206 | 5.079 | 3.596 |
| 2 | 346,823 | 0.230 | 5.776 | 2.398 |
| 4 | 418,469 | 0.281 | 6.852 | 3.340 |
| 8 | 561,761 | 0.379 | 12.281 | 1.969 |
| 16 | 848,345 | 0.561 | 17.513 | 2.997 |
| 32 | 1,421,513 | 0.927 | 未実施（setup打切り） | 1.627 |

全tone基準との差は推定値の一致度であり、実際の呼吸数に対する誤差ではない。Rawに同期した呼吸数正解ラベルが無いため、生体情報としての精度は未確定。

## 実験対象

`zkp/circuits/csi_lomb_scargle_end_to_end.circom` のパラメータ `SUBCARRIERS` のみを 1, 2, 4, 8, 16, 32 に変更し、独立ディレクトリへコンパイルする。既存本番回路は変更していない。64 samples、32周波数bin（約3–24.24 BPM）、正常bin 5..27（約6.43–21.50 BPM）は固定。PCA後の3成分を入力する旧LS回路の比較ではない。

## Rawデータの主評価

- `../common/manifest.json` に記録されたRaw直下8ファイル、各先頭48秒、同じ窓を使用。
- 各ファイルの最頻フォーマットを採用し、**Tx0/Rx0の1アンテナ対**に固定。そのアンテナ対内の物理サブキャリアから選ぶ。PicoScenesのColumnMajor配置の根拠はcommon/README参照。
- tone番号0を起点に、既選択toneから最も遠いtoneを順に追加する決定論的入れ子選択。信号強度や正解呼吸数を使わず、サブキャリア数だけを増やす。
- millisecond量子化で時刻重複を除去し、48秒内の64観測を等間隔**行番号**で選択（不均一な実時刻を保持）。全本数で同じ64行。
- 32候補全体から求めた共有I/Qスケールを、全本数で固定。最大絶対I/Q=1800、12-bit offset=2048に丸める。
- 入力は振幅二乗を回路内で中心化。各SCの正常帯域内最大スコアが最も大きいSCを選び、その帯域内ピークを推定BPMとして出す。全帯域ピークの範囲判定は別出力。
- **Rawに同期呼吸センサーや実測呼吸数ラベルは無い**。Raw結果は「同条件浮動小数点LSとの一致度」「全tone浮動LS基準との推定差」であり、人の呼吸数精度ではない。
- 全tone基準も同じ64観測・同じ32周波数bin・同じアンテナ対を使う。全tone基準が正解という保証はない。
- 同条件浮動LSもms丸め後の時刻を使用する。整数との差が0でも、元のns時刻をmsへ丸める誤差や64点抽出の影響が0とは言えない。
- `preparation_seconds` は32候補の共通準備時間で、各本数固有の前処理時間ではない。

`preprocessing.json` は選択tone番号・行・スケール・参照値を記録する。`accuracy.csv` は8×6条件の個票、`accuracy_summary.csv/json` は本数別平均。

## 整数参照と実回路

`reference.py` は既存回路の整数Taylor sin/cos、16binごとの再アンカー、符号付きrounding、整数Gram式、交差積argmaxをPython任意精度整数で再現する。Python計算時間を証明時間とは呼ばない。

`witness_runner.js` は各本数用にコンパイルされた**実際のWASM**に入力し、Circom sanity assertionsを有効にしてwitnessを生成する。公開4出力（選択SC、推定bin、全帯域bin、正常判定）を整数参照と照合。表のwitness時間はWASMロード・Node起動・ディスク書込を含まない。別列 `witness_process_seconds` はNode起動込み。`preparation_seconds` は共通NPZ読込以降であり、最初のPicoScenesバイナリ解析時間を含まない。

回路はCircom 2.2.3 `--O2` で統一。旧資料のO1制約数とは直接比較しない。compile・trusted setup・鍵contribution・witness・prove・verifyを別々に測る。compile/setup/contributionは本数別回路を準備する一回限りの費用で、毎回の推定・証明時間には加算しない。Groth16 prove/verifyは同一Raw窓に対し各3反復、中央値と最小/最大を記録する。初期zkeyへ暗号論的乱数で追加contributionし、最終鍵を使用する。

## 補足保存のみ：合成対照（今回の報告本編では不使用）

ユーザーの希望に従い、主比較はRaw実データのみとする。下記の既存計算は補足保存し、追加の合成witness検証は実施しない。

`synthetic.py` の40ケース（7.5/10/15/20 BPM×10固定seed）は、32toneのI/Q振幅に既知の正弦波と独立Gaussian雑音を加えたもの。toneごとの雑音標準偏差は50–250、信号振幅100、位相は固定seedのランダム値。各本数は同じ試行の入れ子集合。`synthetic_accuracy.csv` にMAE/1 BPM以内割合の元データを記録する。これは生体計測精度ではなく、指定した合成モデルでの既知周波数推定精度である。

`shared_synthetic_accuracy.csv` はVMDと共通の6合成ケース（9/12/18 BPM×noise 0.02/0.15）の補足。主40ケースと混ぜて平均しない。

`legacy8_sensitivity.csv` は旧edgeの「全flattened CSI列から等間隔8列」を再現した補足。主評価の「1アンテナ対内の物理SC数」と選択方法・スケールが異なるので同じ本数曲線に混ぜない。

## 再実行

repo rootから、numpyを持つPythonで実行する。

```sh
OPENBLAS_NUM_THREADS=1 python3 research/2026-10-26/lomb/run.py --compile
OPENBLAS_NUM_THREADS=1 python3 research/2026-10-26/lomb/run.py --accuracy --circuits
OPENBLAS_NUM_THREADS=1 python3 research/2026-10-26/lomb/run.py --prove --counts 1,2,4
OPENBLAS_NUM_THREADS=1 NODE_OPTIONS=--max-old-space-size=8192 python3 research/2026-10-26/lomb/run.py --prove --counts 8,16 --ptau research/2026-10-26/.cache/ppot_0080_21.ptau
OPENBLAS_NUM_THREADS=1 NODE_OPTIONS=--max-old-space-size=12288 python3 research/2026-10-26/lomb/run.py --prove --counts 32 --ptau research/2026-10-26/.cache/ppot_0080_21.ptau
```

## 限界

一台の開発Mac上のwall-clock測定で、他の研究処理・OS処理の影響を含む。prove反復中はLSのコンパイルを行わない。SC1のsetup開始時だけSC32コンパイル終盤と重複したため、setup時間のサイズ間比較にはこの競合も含まれる。それ以外のLS重処理は逐次実行。処理時間の厳密なハードウェアベンチマークではない。Raw各ファイル1窓のため、独立被験者数や外部妥当性を意味しない。サンプル数64固定で、元データの欠測・疎な観測・短い窓の影響は残る。サブキャリア選択とI/Q量子化は回路外であり、選択の公平性そのものは証明されない。

再現用のprivate入力と巨大なwitness/R1CS/鍵はgit除外。nonce=1は研究用の固定入力（再現性用）であり、本番の秘密nonce生成方針として使用しない。

## 撮影用回路ソース

`circuits/sc1.circom`〜`sc32.circom` は実際にコンパイルしたソースのbyte-identicalコピー。末尾mainのサブキャリア数が各実験値。原文コメントには8本と記載された箇所が残るが、実パラメータはmainの値を参照する。コード撮影にはこの末尾を使える。

## 証拠ファイル

`evidence/sc*/` に各3反復の公開proof・public signal・verification key・実行ログを保存する。`evidence_manifest.json` にSHA-256を記録。例えばrepo rootで `zkp/node_modules/.bin/snarkjs groth16 verify research/2026-10-26/lomb/evidence/sc8/verification_key.json research/2026-10-26/lomb/evidence/sc8/public0.json research/2026-10-26/lomb/evidence/sc8/proof0.json` を実行すれば、巨大なR1CSやproving key無しに保存証明を再検証できる。

## 32本のsetupで確認したメモリ上限

32本のGroth16 setupは `NODE_OPTIONS=--max-old-space-size=8192` でV8 heap不足となり、exit -6で終了した。これは証明生成（prove）ではなく鍵setup工程の失敗。ログとV8 GC値は `failures/` に保存。`--max-old-space-size=12288` へ増やした再試行も1800秒の打切り上限に達し、setupは未完了。1800秒は正常完了時間ではない。32本のprove/verifyは未実施で、`proof_summary.json` の該当時間はnull、statusは`setup_timeout`。タイムアウトした`initial.zkey`は無効な部分ファイルであるため削除した。8GB時の失敗も含めて両attemptを残している。`sc32_setup_resource_samples.csv` は再試行の5秒間隔RSS観測で、真のピークの下限であり、V8 heap上限と同じ指標ではない。
