# VMD比較回路そのものへの中間public追加・再測定

旧診断の別実行結果は使わない。K×Rの36比較設定と初期配置候補1設定の**各比較回路そのもの**に、入力、DFT、全反復全モードの実虚係数、中心軌跡を実内部から `<==` 接続した。この回路の各Groth16 proofが出すpublic値だけを、その実測runの波形・スペクトルとして表示する。

本編はRaw直下8記録のみ。`common/windows/csi_*.npz`の既存signal128をそのまま使い、前回と入力波形をそろえる。生理GTはなく、推定値・手法間一致度の比較である。合成データは使用しない。

## 測定設計

- K=1/2/3/4/5/8 × R=1/2/4/8/16/32。初期中心は既存prefix `[8,24,48,16,32,56,40,4]`。
- 候補はK3/R4、初期中心 `[8,16,24]`。
- 各構成でRaw8件を1proofずつ、034004代表収録を追加2proof。計10proof/config。
- 推定値集計はrepeat0の8件のみ。代表のprove中央値はその収録の3回のみで計算し、他収録の時間を混ぜない。
- compile/setup/contribution/witness/prove/verifyを別記。witnessは1回の計算でWTNS生成と公開値抽出を行い、計算単体とプロセス全体の時間を区別する。
- 公開値を増やした結果の制約・鍵・証明生成時間を測るため、旧通常回路のベンチマークとは別結果とする。

## 検証と保存

runごとに証明正常verify、同WTNSから抽出したpublicとの一致、公開mode係数の1値改変の拒否を確認する。schemaの全index/shapeを当該コンパイルSYMと照合。proof publicから復号した入力・DFT・全反復係数・中心・推定結果を独立整数参照と比較する。

`{config}/runs/{window}_repeat{0,1,2}/` の `manifest.json` に実測状態と入力NPZ/inputJSON/回路source/R1CS/WASM/vkey/proof/public/traceのSHA-256を保存する。`trace.json`も同じbindingを保持する。全公開field値は`public.json`に10進文字列で保持し、巨大hashを浮動小数へ変換しない。

表示は`runs_index.json`からverifiedなmanifestだけを選ぶ。`trace_from=public.json`であり、参照計算値や別診断のpublicを表示用原本にはしない。逆DFT、power、モード和、residualは回路外の描画変換であり、回路が時間波形の再構成処理自体まで証明したとは表現しない。

## 容量・未実行の扱い

制約見込みは旧実測に基づく `72876+20589*K*R+6931*K`。実compile後に制約数＋公開入出力数を含む保守的必要powerでptau19/21を選ぶ。ptau19は既存、ptau21は `../../.cache/ppot_0080_21.ptau`。

K4/R32、K5/R32、K8/R16はptau22、K8/R32はptau23相当が必要と見込まれ、利用可能ptau21を超えるため**resource_limit（未実行）**。K3/R32は2^21の上限に近く、実compile値による判断が必要。

全37構成の大型build/keyを保持すると概算44 GiB。最大対応構成の一時成果物は約2.70 GiB、全runの保持public/trace等は概算1.18 GiB（実測サイズではない）。逐次実行し、全10proof/公開値/vkey/source/hash/logを保存・検証した構成だけ`--prune-large`で専用build/keyを削除できる。通常回路・旧診断・他構成を削除しない。

タイムアウト/OOM/ディスク不足/ptau不足はstatusへ記録し、未実行を成功にしない。各重処理は既定1800秒でプロセスグループを停止する。メモリ使用はmacOS `/usr/bin/time -l`の最大RSS、空きディスクは構成開始前に検査する。概算はRAM上限内の完走を保証しない。

## 実行

他担当の証明計時と重ならないようrootが一構成ずつ順序を調整する。source準備だけならgenerateはcompile/proveを開始しない。

```bash
python3 zkp/experiments/2026-10-26/remeasure_public/vmd/generate.py
python3 zkp/experiments/2026-10-26/remeasure_public/vmd/run.py --config k3_r4 --prune-large
python3 zkp/experiments/2026-10-26/remeasure_public/vmd/run.py --config k3_r4_centers8_16_24 --prune-large
python3 zkp/experiments/2026-10-26/remeasure_public/vmd/run.py --config k4_r4 --prune-large
```

続いてk3_r1、k3_r8、その後小型順、k3_r32は後半。既存verified runは保存ハッシュとsource/vkeyを確認して再実行しない。例示manifestは`manifest_example.json`で、実験成功を示すものではない。

## 再開・資源制限の運用

代表のrepeat1/2はrepeat0/input.jsonをbyte単位でコピーし、nonceを含む同一入力で3回を測る。完了/pruned構成は開始時に全10manifestと保存artifact/source/vkeyハッシュを確認してskipする。

実compile制約数が1,000,000を超えるとNode heapを最低12,288 MiBへ上げる。各失敗/timeoutはpartial buildのサイズとSHA-256を記録した後、`--prune-large`指定時はその構成のbuildだけを削除する。再試行時に既存compile.jsonがあってもR1CS/WASM/SYMがなければ再コンパイルする。

失敗したattemptに既に成功proofが含まれる場合、再setupで生成される新vkeyに旧proofを誤って紐付けない。旧runs/vkey/source/schema/log/hashを一緒に`archived_attempts/`へ保存し、新しいattemptは全runを新規計測する。過去attemptは主runs_indexへ混ぜない。未実行の容量超過4構成もrun.pyのpreflightでresource_limitを記録済み。
