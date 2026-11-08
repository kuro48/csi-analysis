# CSI Lomb–Scargle Edge Prover

秘密のCSI I/Qから、Lomb–Scargle呼吸推定のGroth16証明を端末内で生成する
自己完結パッケージ。生CSI、回路入力、witnessは外部へ送信しない。

## 必要環境

- Linux/macOS x86_64またはARM64
- Node.js 18以上（20推奨）
- Python 3.10以上
- `.csi` / `.npz` の入力変換にはNumPy
- `.csi` を直接処理する場合のみ:
  - PicoScenes Python Toolbox

回路のコンパイル、Circom、snarkjsのnpmインストール、ptauは端末側では不要。
WASM、proving key、verification key、snarkjs CLIを同梱している。

> Gitリポジトリでは、GitHubの通常ファイル上限を超えるproving key（`.zkey`）を管理しない。
> エッジ配布パッケージまたは別の成果物ストレージから
> `artifacts/csi_lomb_scargle_end_to_end_final.zkey`を配置して使用する。

## 1. 配置確認

```bash
cd lomb_scargle_e2e
python3 bin/verify_manifest.py
```

## 2. 自己診断

```bash
./bin/self_test.sh
```

合成された15 BPM相当の秘密CSIからwitnessとGroth16証明を生成し、ローカル検証する。

## 3. PicoScenes CSIを証明

```bash
./bin/prove.sh /path/to/capture.csi ./proof_result.json
```

出力される `proof_result.json` にはGroth16証明と公開信号だけが入る。秘密CSI、nonce、
量子化後I/Q、witnessは一時ディレクトリで処理され、成功・失敗にかかわらず削除される。

元の `.csi` も証明成功後に削除する場合:

```bash
DELETE_SOURCE_AFTER_PROOF=1 ./bin/prove.sh /path/to/capture.csi ./proof_result.json
```

この設定は元ファイルを削除するため、運用ポリシーを確認してから使用する。

## 4. NPZ入力

PicoScenes以外から渡す場合、次の配列を持つNPZを利用できる。

- `csi`: `[samples, subcarriers]` のcomplex配列
- `timestamps_ns` または `timestamps_ms`: `[samples]`

```bash
./bin/prove.sh capture.npz proof_result.json
```

## 5. 正規化済みJSON入力

回路入力JSONを直接渡すこともできる。

```bash
./bin/prove.sh input.json proof_result.json
```

必要キー:

- `csiI[64][8]`
- `csiQ[64][8]`
- `commitmentNonce`
- `timestampsMs[64]`

## 6. 証明だけを検証

```bash
./bin/verify.sh proof_result.json
```

`OK!` が表示されれば検証成功。

## 入力変換仕様

`.csi` 入力では次を決定論的に実行する。

1. `systemns` とCSIを持つフレームから最頻CSI幅を選ぶ。
2. 時刻順に整列し、1 ms量子化後の重複を除く。評価用に最大1,024観測を決定論的に取り出す。
3. 全候補列について、振幅の相対変動、外れ値、時刻を考慮した局所残差ノイズを評価する。
4. 品質スコアの上位候補から、波形の重複も減点して8列を選ぶ。正常BPM帯域は選択基準に使わない。
5. 全収録区間から等間隔に64観測を選ぶ。選ばれた列の元のI/Qを使い、選択用のクリップ・トレンド除去は回路入力に適用しない。
6. 選択I/Q全体へ共通スケールを適用し、最大絶対値を1800へ合わせる。
7. `[-2048, 2047]` に制限し、2048を加えて12-bit値にする。量子化後にパワーが一定となる列は事前エラーにする。
8. 暗号学的乱数から秘密Poseidon nonceを生成する。

回路外の8列選択は `motion-quality-v1`、回路内のLomb–Scargle処理と鍵は従来のまま。
**全候補からの選択の正しさは証明していない。** 回路は渡された8列のI/Qからの計算を証明する。
公開結果の `selectedSubcarrier` は8列内のスロット番号（0〜7）で、元データの列番号やRFサブキャリア番号ではない。
複数アンテナの場合、候補番号はflatten後のCSI配列の列番号である。

旧方式との比較:

```bash
CSI_SUBCARRIER_SELECTION=uniform ./bin/prove.sh capture.csi uniform_result.json
CSI_SUBCARRIER_SELECTION=motion-quality ./bin/prove.sh capture.csi adaptive_result.json
```

ローカルで選択理由を確認する場合（保存先は新しいファイル名を指定）:

```bash
CSI_SELECTION_METADATA_FILE="$PWD/private/selection.json" ./bin/prove.sh capture.csi proof_result.json
```

このメタデータは0600で保存し、公開proof結果には追加しない。個別の選択列・品質スコア・入力スケールを含む。
直接変換する場合は `python3 bin/prepare_input.py capture.csi input.json --metadata selection.json --selection motion-quality`。

動的な列が8本未満、時間情報が不正、量子化で波形が消える場合はエラーになる。動きが弱くスコアがゼロの候補を補充した場合は、ローカルメタデータの `low_quality_fallback` がtrueになる。
本選択スコアは体動の原因や呼吸の正解を保証しない。呼吸器や映像などの正解値との比較は別途必要。

サブキャリア番号、入力スケール、入力振幅の統計値などの変換メタデータも公開結果には
含めない。変換用一時ファイルはwitnessとともに実行終了時に削除される。

## 公開情報

- CSI Poseidonコミットメント
- 公開相対タイムスタンプ64点
- 選択サブキャリア番号
- 正常帯域内推定周波数/BPM
- 全帯域グローバルピーク/BPM
- 正常判定
- Groth16証明

## 注意

- 本回路は64サンプル、8サブキャリア、32周波数binのfeasibility版。
- 全探索範囲は約3～24 BPMで、正常範囲は約6.43～21.50 BPM。
- 現行PythonのSNR選択、Butterworth、PCAを再現するものではない。
- 初回実CSI運用前に、既知BPMとの精度評価と端末上の処理時間・メモリ測定が必要。
