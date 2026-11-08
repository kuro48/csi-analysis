# Lomb–Scargle入力のサブキャリア選択改善

既存の等間隔8列選択を、全候補の振幅変動とノイズを評価する `motion-quality-v1` に変更した。対象は `edge/lomb_scargle_e2e` の生CSI→Circom経路。別系統のPCA入力版Lomb–ScargleやFabricの一出力呼吸証明は変更していない。

## 選択方法

振幅の分散を手掛かりにサブキャリアを選ぶ方法は、[Monitoring Vital Signs and Postures During Sleep Using WiFi Signals](https://mosis.eecs.utk.edu/publications/liu2018monitoring.pdf) などでも用いられている。今回のスコア式と閾値はこの実装独自のヒューリスティックで、論文の方式をそのまま再現したものではない。

1. 各列の `abs(CSI)` を時間方向の振幅中央値で正規化する。絶対的な電波強度だけで上位を決めない。
2. 非有限値、極端に弱い列、量子化後にパワー変動が消える列を候補から除く。弱い列の閾値は非ゼロ列の振幅中央値の1%（パワー換算約−40 dB）。
3. 中央値からの変動を6 MAD（1.4826補正）でクリップし、直線的なドリフトを取り除く。この処理は評価用のみ。
4. 実際の不均一時刻に従い、前後の点から内挿した値と中央点の差を計算する。そのMADから白色ノイズ相当の分散を推定する。
5. 次のスコアで順位を決める。`V` は正規化・外れ値処理・トレンド除去後の分散、`N` は残差から推定したノイズ分散、`p` は外れ値率。

   `score = max(V − N, 0)² / V × (1 − p)²`

6. 上位64候補の中から8列を逐次選択する。既選択列との最大絶対相関を `r` として、`score × (1 − 0.25 r²)` で似た波形を減点する。これは弱い減点で、隣り合う周波数や似た波形の選択を禁止する規則ではない。
7. 同点は変動量、元の列番号の順で決める。評価用間引きも固定seedなので、同じ入力なら同じ8列になる。nonceのみ乱数。

正常とされるBPM帯域や最終的な `isNormal` はこの選択基準に使わない。正常な周期を選好して異常な動きを捨てる方向へのバイアスを避けるためである。一方、現在の回路内の「正常帯域ピークが最大の列を選ぶ」計算は従来どおりで、この回路上の性質までは解消していない。

体動はCSIの変化を生む要因の一つだが、この選択は人の動きと電波干渉・マルチパス変化を識別する検出器ではない。振幅の変化を使うため、純粋な位相変動だけに現れる情報も評価しない。

## 証明範囲

現在の等間隔8列選択もPythonで行われていた。今回も効率を優先してこの境界を維持し、**8列への選択自体はCircomの証明対象外**とした。

- 回路は選ばれた8列・64観測のI/Q、Poseidonコミットメント、Lomb–Scargle計算と判定を検証する。
- 全候補からその8列を選んだ理由、除外した列、元の生CSI全体との対応は証明していない。
- 元のI/Qをそのまま選び、従来と同じ共通スケールで量子化する。選択用クリップ・トレンド除去を回路入力へ流用しない。
- 回路ソース、WASM、公開信号69個の形式、proving/verification keyを変更していない。制約数は807,453のまま。
- 全候補からの選択も証明したい場合は、全候補のコミットメントとスコア計算・順位/所属の制約を追加した新回路・鍵が必要。この実装では未実施。

公開 `selectedSubcarrier` は入力8列内のスロット番号（0〜7）。元の列番号はローカルメタデータにだけ保持する。PicoScenesの複数送受信アンテナのCSIはflattenされた配列なので、列番号をそのまま物理的なRFサブキャリア番号と解釈しない。

## 処理量と失敗時の動作

PicoScenesは2パスで読み込み、最頻CSI幅を特定してタイムスタンプを整列・重複排除する。評価用には最大1,024観測、回路用には64観測を保持するため、全幅の配列として保持する行数は最大1,088。PicoScenesパーサーのバッチは32フレーム。

選択の処理量は概ね `O(T×S + S log S + T×64×8)`。全サブキャリア間の巨大な相関行列や全候補ごとのLomb–Scargle計算はしない。NPZは圧縮ファイル自体を読み込む必要があり、ファイル全体のメモリ使用まで一定にはできない。

動的な列が8本未満なら明示的なエラーとし、同じ列の重複で埋めない。選ばれた8列を共通スケールで量子化した後、パワーが一定になる列があればwitness生成前に停止する。低品質候補で8本を補充した場合はローカルメタデータの `low_quality_fallback=true` で記録する。このフラグは暗号検証済みの品質判定ではない。

## 使い方

```bash
# 新方式が既定
PYTHON_BIN="$PWD/.venv/bin/python" \
  bash edge/lomb_scargle_e2e/bin/prove.sh capture.csi adaptive-proof.json

# 従来の等間隔方式
CSI_SUBCARRIER_SELECTION=uniform PYTHON_BIN="$PWD/.venv/bin/python" \
  bash edge/lomb_scargle_e2e/bin/prove.sh capture.csi uniform-proof.json

# 選択列とスコアをローカルで確認（新規ファイルのみ）
CSI_SELECTION_METADATA_FILE="$PWD/.local/selection-debug.json" \
  PYTHON_BIN="$PWD/.venv/bin/python" \
  bash edge/lomb_scargle_e2e/bin/prove.sh capture.csi proof.json
```

`.csi` と `.npz` に対応する。正規化済み `.json` を直接入力する場合は、既に8列に絞られているため選択処理を実行しない。受信端末の既存配布物を更新する場合は、`prepare_input.py`、`select_subcarriers.py`、`prove.sh`、README、VERSION、MANIFESTを一緒に更新する。回路や鍵の再配布は不要。

## 評価と再現

[比較JSONと図・実証明](progress/subcarrier-selection/) に保存。合成データでは、80列の中で位置をランダムにした8列だけに15 BPMの振幅変調を与え、静止・白色ノイズ・極小振幅・単発スパイクを混ぜて20seedで比較した。これは制御された例であり、実CSIでの体動認識率や呼吸精度ではない。

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 DEBUG=true ZKP_AUTO_COMPILE=false \
  .venv/bin/python -m pytest -p pytest_asyncio.plugin -o addopts='' \
  backend/tests/unit/test_edge_subcarrier_selection.py -q

mkdir -p .local/subcarrier-selection/circuit
circom zkp/circuits/csi_lomb_scargle_end_to_end.circom --O1 --r1cs --wasm --sym \
  -o .local/subcarrier-selection/circuit -l zkp/node_modules
.venv/bin/python scripts/benchmark_subcarrier_selection.py \
  --csi sampledata/csi_20260519_114943.csi \
  --output .local/subcarrier-selection/comparison.json \
  --r1cs .local/subcarrier-selection/circuit/csi_lomb_scargle_end_to_end.r1cs
```

比較スクリプトの入力JSON・witnessは `.local/subcarrier-selection/comparison` に保存し、公開比較JSONには含めない。実CSIの正解ラベルはなく、そこでの判定値の変化を精度向上とみなしてはいけない。実CSIの前処理時間は1回ずつの参考測定で、読み取り順序・OSキャッシュの影響がある。今回の目的は選択する情報の質を改善することであり、等間隔選択よりCPU処理時間を短縮するものではない。
