# 実測CSIの時刻点数・周波数グリッド数比較

時刻点数 N = 64 / 96 / 128 と、周波数グリッド数 K = 32 / 64 / 128 の9条件を比較する。合成CSIは使わない。正解呼吸数のラベルがないため、評価対象はPython参照との差・一致であり、生理学的な正解率ではない。

実測結果・グラフ・公開証明・計測ログは[9条件の比較結果](progress/2026-11-16-frequency-grid/README.md)に保存している。

## 固定する条件

- 前回の `.local/sample-count/inputs` にある実測入力をハッシュ確認して再利用する。時刻点・全候補I/Q・共有スケール・nonceを変更しない。
- 各ファイルは同じ観測区間を使う。Nごとの時刻点は観測番号のrounded linspaceであり、入れ子ではない。Kだけを変える場合は時刻点も選択列も同一。
- サブキャリア選択は従来のCircom内スコアのまま。Pythonで列を選んで回路へ渡す構成にはしない。
- LSの探索範囲は既存32点回路の端点 `127/2540`〜`1026/2540` Hzに固定。
- グリッドは `f_j = 127/2540 + j * 899/[2540*(K-1)]`、`j=0..K-1`。
- 正常帯域は6〜22周期/分に固定。該当binはK32:5〜27、K64:9〜56、K128:18〜113。
- グリッドは入れ子ではない。Kを増やすと内側の周波数候補の位置も変わる。
- 固定小数点のsin/cos回転を16binごとに再アンカーする方式も維持する。グリッド増加に伴う丸めや僅差ピークの交代は、同入力・同グリッドの実数Pythonとの比較で別途調べる。

## Python参照

1. **同入力・同グリッド整数Python**：回路の整数演算を再現。選択列を含む実際の回路出力と一致を確認する。
2. **同入力・同グリッド実数Python**：正確なsin/cosを使用。固定小数点演算の影響を調べる。
3. **同時刻点・2,048周波数Python**：回路と同じ選択列・量子化CSI・時刻点を使う。グリッドの刻みを細かくする効果を見る。
4. **全時刻点・2,048周波数Python**：元の全時刻点で従来と同じスコアを使って列を選択。9条件共通の主参照。4,096周波数でもピークを確認する。
5. **前回の独立Python選択法**：floating-mean LS適合度による選択、355周波数。前回の実測参照値をハッシュ確認して再利用する。この旧方式は旧32binの帯域端を使い、帯域内の実際の候補は約6.4794〜21.4767周期/分。今回の主参照の6〜22周期/分とは異なる。

2〜4は現行回路と同じ平均除去した電力波形・sin/cos適合モデル。5は選択式・LSモデル・周波数グリッド・帯域定義が異なるため、表を分けて解釈する。

前回の「同式全点Python」は32周波数だった。今回の主参照は2,048周波数なので、K32の回路出力が同じでも差の数値は前回と変わる。

## 回路と互換性

- [グリッド対応回路](../zkp/circuits/lomb_scargle_adaptive_grid.circom)
- [研究用LSコア](../zkp/circuits/lomb_scargle_csi_grid_core.circom)
- [可変グリッドのsin/cos生成](../zkp/circuits/lomb_scargle_timestamp_grid_basis.circom)
- [6条件のmain](../zkp/experiments/frequency-grid/)

既存テンプレート・回路ソースは変更せず、研究用のLSコアとグリッドを別ファイルに実装する。整数sin/cosの原始部品は既存テンプレートを再利用する。既存の配備済み鍵・回路成果物は置換しない。実験ごとに新しいR1CS・Groth16鍵・EVM検証器・Fabric chaincode namespaceを使う。

公開信号は従来と同じN+6個。Kは回路・検証鍵・配備manifestで固定される。Fabricは `frequency-grid-v1` プロトコルでN・K・候補容量・回路名・公開入力数を厳密に検査する。

周期の剰余計算に必要なビット幅はK32:22、K64:28、K128:29。時刻は24bit、最大周波数は固定なので周期商は16bit以内。LS比の比較幅はN64:236bit、N96/N128:246bitで従来通り。グリッド数は個々の周波数での積和の上限を増やさない。

## 再実行

前提：前回の実測入力・測定成果物、Circom、native prover、Node依存、Python `.venv`、ローカルGanache/Fabricが存在すること。秘密鍵をチャットやGitへ出さない。

```bash
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python scripts/evaluate_frequency_grid.py prepare

OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python scripts/run_frequency_grid_experiment.py

.venv/bin/python scripts/report_frequency_grid.py

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  .venv/bin/python -m pytest scripts/test_frequency_grid_real.py -q
node --test fabric/test/sample-count-protocol.test.mjs
```

`prepare` は既存の参照を上書きしない。再開はpipelineコマンドを使う。ソースハッシュが変わった場合は止まり、既存の測定を新しい実装の実測として扱わない。

状態は `.local/frequency-grid/pipeline-state.json`、進行ログは `pipeline.log`。コンパイル、witness、鍵生成、証明、デプロイ、記録・検証を順に行う。重い処理を並行して台帳の時間に混ぜない。

研究用Fabric配備が承認待ちで失敗した場合は、peer/ordererの状態を調べ、既存の `fabric/scripts/deploy-adaptive.sh` に実験用の `FABRIC_WORK_DIR`・`FABRIC_CHAINCODE_NAME`・manifest・検証鍵と `FABRIC_RESUME=true` を指定して再開できる。計測開始前に両組織の配備とgatewayの設定一致を確認する。

## 時間の測り方と限界

- 代表実測CSI `csi_20260519_114943`、全4,004候補。証明生成と記録は各条件1回。
- 証明処理時間は鍵・R1CS・witness読み込み、群検査、全制約検査、生成、native検証を含む。witness計算・setup・配備は別。
- EVM記録：gas見積もり後、送信から成功receiptまで。RPCキャッシュを無効化、receiptポーリング100ms。
- Fabric記録：endorse開始からcommit成功まで。
- 検証：初回＋追加10回。表には追加10回の中央値を載せ、全反復値をJSONに保存する。
- EVMは `eth_call`、Fabricは `evaluateTransaction`。新たな検証トランザクションの確定時間ではない。
- K32の証明・時間は前回の実測値を再利用。追加6条件は直列実行する。小さな時間差の統計的有意性を主張しない。
- ローカルEVMとローカルFabricの測定であり、Sepoliaの時間・金額やFabricの運用費用の比較ではない。
- 16GiBホストではswapの影響がある。結果を別マシンの速度として一般化しない。

完了時の数値・グラフ・公開証拠は `docs/progress/2026-11-16-frequency-grid/` に出力する。生CSI・private witness・proving keyは `.local` に保存する。
