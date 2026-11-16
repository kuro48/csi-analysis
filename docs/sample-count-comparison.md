# 実測CSIによる時刻点数の比較手順

対象は64・96・128点。合成CSIは生成・使用しない。点数の変更による参照差と、実際のGroth16証明・台帳処理の時間を分けて測る。
既存64点を基準に1.5倍・2倍を比較する。対象5ファイルの最小全点数は150点なので、128点までは全件を補間なしで比較できる。

今回の数値・図・証明・台帳の取引IDは[実測結果レポート](progress/2026-11-16-sample-count/README.md)を参照。

## 条件を揃える

- 同じ実測CSI 5ファイル、同じパーサー、同じ観測区間、同じ全候補列を使用する。
- 最頻CSI幅のプールを使用し、時刻を並べ替え、同じミリ秒に丸められるフレームは最初の1件を残す。
- 全観測点から1つの共有I/Qスケールを決め、64・96・128点で固定する。点数ごとに別のスケールを計算しない。
- 各点数の行は観測番号に対する `round(linspace(0, M-1, N))` で選ぶ。先頭・末尾を共有するが、各行集合は入れ子ではない。
- 全候補を同じ容量4,004の回路に渡す。実測53列のファイルは残りを正規のゼロパディングとする。
- Lomb–Scargleは同じ32bin、`f(bin)=(127+29*bin)/2540 Hz`。点数を増やしても周波数刻みそのものは変えない。

64点版は既存のWASM・R1CS・鍵を再利用する。スケールを全点共通にするため、以前の「選んだ64点だけからスケールを求める評価」と完全に同一の入力とは限らない。

## Pythonとの比較

1. **整数・同入力参照**：任意精度整数の選択計算と、回路と同じ固定小数点三角関数・LS計算。回路の実装一致を検査する。
2. **実数・同時刻点参照**：回路と同じ整数化済みI/Q、同じ時刻、同じ32binを使い、Pythonの実数sin/cosとLSで比較する。
3. **整数化前・同時刻点参照**：共通スケール適用後、整数化する前のI/Qで比較する。
4. **実数・全点参照**：同じ選択式を全観測点へ適用し、その選択列に同じ32binのLSを適用する。
5. **同一列・全点参照**：回路が選択した列を固定し、全観測点でLSを計算する。列の選択差と時刻点数の差を切り分ける。

実数LSは、電力を平均除去してからcos/sinを当てはめる現行回路と同じモデル。周波数ごとに定数項も当てはめる別のfloating-mean選択基準とは混同しない。

選択列の一致、全域ピークbinの一致、ピーク周波数の差、`isNormal`の一致を記録する。正常帯域内の最大binと全域最大binは別の出力であり、主な周波数差には全域最大binを用いる。

正解の呼吸数・体動ラベルは未提供。ここでの「精度」はPython参照との一致・差であり、実際の呼吸数に対する正解率ではない。点数を増やして差が小さくなることを前提に結果を選別しない。

補助比較として、前回の独立したPythonスペクトル選択法も再計算する。呼吸帯域のfloating-mean LS適合度で列を選ぶ355周波数点の参照で、全点参照と同じ採用点数の参照を保存する。
回路とは選択式・LSモデル・周波数刻みが異なるため、上記の同式比較とは別の表にする。これも正解ラベルの代わりにはならない。

## 回路の数値範囲

`CSIMotionSelector` を最大128点まで拡張し、64点以下の制約は維持する。

- 64点以下：比較幅30 / 59 / 240ビットを維持。
- 65～128点：合計電力31ビット、変動比較61ビット、スコアの交差乗算比較248ビット。
- 128点以下では、選択スコアの交差乗算は `2^242` 未満でBN254の範囲内。
- LSの交差乗算は、入力電力上限とGram行列の射影の性質から `N^10 * 2^172` 以下。128点では `2^242` 以下なので、新しい構成では246ビット比較を使う。
- 公開出力5個＋時刻N個＋候補数1個で、公開信号数は70 / 102 / 134になる。

既存64候補・64点回路を再コンパイルしたR1CSのSHA-256は、既存ファイルと同じ
`3da8c58da7cd1bb93185ef7fc5de76bf03b03d8ad025a321bee5f8eb3c1f70f8`。
96・128点は新しいmainと検証鍵が必要であり、64点用の鍵は流用しない。

## 証明と台帳の測定

代表実測CSIは `csi_20260519_114943.csi`。候補数4,004と観測区間を固定し、各点数の実際の証明を生成する。

| 項目 | 測定範囲 |
|---|---|
| witness | WASM読み込みから、sanity check付きwitness計算完了まで |
| 証明処理 | R1CS・witness・鍵読み込み、鍵の群検査、全制約検査、Groth16証明生成、nativeローカル検証 |
| EVM記録 | トランザクション送信開始から成功receipt取得まで。gas見積もりは外。polling 100ms |
| Fabric記録 | endorse開始からsubmitとcommit成功確認まで |
| EVM検証 | 保存済み証明を検証する`eth_call`の往復時間 |
| Fabric検証 | peer内のchaincodeで保存済み証明を検証する`evaluateTransaction`の往復時間 |
| ローカル検証 | 同じ公開入力・証明・鍵をsnarkjsで検証する時間 |

記録は各条件1回、検証は初回＋追加10回。追加10回の中央値・最小・最大と全測定値を保存する。同じ証明を繰り返し照会する値であり、独立した10人分の実験ではない。初回値も、未起動プロセスのコールドスタートを保証する測定ではない。

鍵生成・デプロイはオンライン処理時間に含めない。重い処理は直列実行し、台帳計測と他条件のコンパイルを重ねない。

EVMはローカルGanache（chainId 1337）、Fabricは既存のローカルコンソーシアムネットワークを使用する。各点数専用の検証器・レジストリ・`csisamples...` chaincodeを新設し、既存の観測記録を置き換えない。Sepoliaの実測や本番の費用として扱わない。Fabricのインフラ費用は計上しない。

保存後に正しい証明の検証成功を確認し、実測証明の`isNormal`公開値だけを改ざんした負例がローカル、EVM、Fabricで拒否されることも確認する。

セットアップは既存と同じnative arkworksのテスト用単独セットアップ。MPC ceremonyや本番向けセットアップとは区別する。

## 実行手順

```sh
# 実測データから全条件の入力とPython参照を作成（既存の準備結果は上書きしない）
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python \
  scripts/evaluate_sample_counts.py prepare

# 大きな回路のコンパイル、実行、鍵生成、証明、ローカル台帳への配備と測定を直列実行
.venv/bin/python scripts/run_sample_count_experiment.py

# 実測入力・数値範囲・完了済み回路出力の確認
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest scripts/test_sample_counts_real.py -q
node --test fabric/test/sample-count-protocol.test.mjs

# 全条件が完了してからJSON・Markdown・図を作成
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python \
  scripts/evaluate_sample_count_spectral.py
.venv/bin/python scripts/report_sample_counts.py
```

途中の状態は `.local/sample-count/pipeline-state.json` に保存される。各段階は完了済みの成果物を再利用する。失敗途中の鍵を黙って上書きしない。作業フォルダーには秘密入力・witnessも含まれるため、Gitへ追加しない。

結果レポートには公開証明、検証鍵、取引ID、計測値を保存し、生CSIや秘密nonceは含めない。

## ローカルFabricの接続復旧について

今回の96点版の配備時には、peerのorderer接続が `too_many_pings` で切断され、1時間の再接続待ちとなっていた。
承認はordererに届いていたがpeerがブロックを受信できず、CLIの確定待ちがタイムアウトした。
両peerを再起動して同期を回復し、`fabric/scripts/deploy-adaptive.sh` の `FABRIC_RESUME=true` を使って未完了の承認・commitを再開した。
このスクリプトは `FABRIC_CHAINCODE_NAME` で研究用namespaceも指定できる。既定値は従来の `csiadaptive4004`。
両組織のcommit結果とgatewayのdeployment IDを確認した後に測定を開始しており、復旧時間は記録・検証時間に含まない。
詳細は実験フォルダーの `n96/fabric/deploy.log` と `resume.log` に残している。

関連実装：

- [可変時刻点数の回路](../zkp/circuits/lomb_scargle_adaptive_samples.circom)
- [入力と参照・回路実行・証明](../scripts/evaluate_sample_counts.py)
- [台帳への配備・記録・検証の測定](../scripts/sample_count_ledgers.mjs)
- [結果集計](../scripts/report_sample_counts.py)
