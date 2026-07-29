# zkVM vs Python + Circom 時間計測

RISC Zero zkVM と既存の Python 5-1 解析 + Circom/Groth16 証明書方式を、
計測範囲を明記した JSON として保存する。

## 比較する時間

実行時間は PicoScenes の parse を除外し、両方式へ同じ複素 CSI 行列を渡す。

| 方式 | 内訳 | `total_execution_seconds` |
|---|---|---|
| Python + Circom | Python 5-1解析、witness、Groth16 prove、verify | 4工程と初期化の合計 |
| zkVM | 固定小数点入力化、JSON化、RISC Zero prove + receipt verify | 3工程の合計 |

zkVM は CSI から固定アルゴリズムを再実行する一方、Circom は Python/VMD の
出力特性を certificate 回路で検査する。保証する命題が異なるので、時間差は
「同一計算の実装差」ではなく「現在の2つの検証方式のシステムコスト」として扱う。

ビルド時間も定義が異なる。

- Python + Circom: 依存導入と Powers of Tau 生成を除外し、回路コンパイル、
  Groth16 setup、contribution、verification key export を計測する。
- zkVM: 本番 `zkvm/Dockerfile` の deployment build を計測する。
  `--no-cache` では OS package、RISC Zero toolchain、Cargo依存取得も含まれる。
  したがって論文等では各内訳と cache 条件を必ず併記する。

## 1. 実行時間

稼働中の backend コンテナにある Python/Circom 環境と zkVM バイナリを利用する。
第1引数に、ユーザーが用意した PicoScenes `.csi` ファイルを指定する。ファイルは
コンテナへ read-only mount され、変更されない。合成データへのフォールバックはない。

zkVM の計算量は入力要素数に大きく依存するため、最初は同じ実 CSI 行列の一部で
スケーリングを確認する。

```bash
research/zkvm-comparison/run-execution-in-docker.sh \
  /path/to/measurement.csi \
  --method both \
  --sample-limit 3000 \
  --subcarrier-limit 8 \
  --output /results/real-3000x8.json
```

既定では zkVM 入力が200万要素を超えると誤実行を防ぐため停止する。用意したファイルの
全行列を意図して測る場合のみ、limitを外して `--allow-large-zkvm-input` を付ける。

```bash
research/zkvm-comparison/run-execution-in-docker.sh \
  /path/to/measurement.csi \
  --method both \
  --allow-large-zkvm-input \
  --output /results/real-full.json
```

複数回計測は `--runs 3`、warm-up は `--warmups 1`。両方式の実行順は run ごとに
反転し、順序バイアスを抑える。ファイルの parse/load 時間は JSON に記録するが、
どちらの方式にも共通なので `total_execution_seconds` からは除外する。zkVM 証明に
タイムアウトは設定せず、完了まで待つ。SIGKILL・その他のエラーになっても、既定では
`status=failed` と `elapsed_before_failure_seconds` を結果へ保存する。即時停止が
必要なら `--fail-fast` を指定する。

CSI読み込みと結果出力は、次のフィールドで確認できる。

- `input.csi_read_seconds`: `.csi` の読み込み・PicoScenes parse・行列化
- `result_output_seconds`: 結果JSONの主書き込み

`result_output_seconds` をJSON内へ記録するための小さな再書き込みは計測外であり、
`result_output_metadata_rewrite_excluded=true` として明記される。

## 2. Circom ビルド時間

ホストにある `circom`、`snarkjs`（または `zkp/node_modules/.bin/snarkjs`）と既存
ptau を使い、一時ディレクトリでビルドする。既存の `zkp/build` と `zkp/keys` は
上書きしない。

```bash
python3 research/zkvm-comparison/benchmark.py build-circom \
  --output research/zkvm-comparison/results/build-circom.json
```

## 3. zkVM ビルド時間

cache 有効の本番 Docker build:

```bash
python3 research/zkvm-comparison/benchmark.py build-zkvm \
  --output research/zkvm-comparison/results/build-zkvm-cached.json
```

完全な deployment build は時間・通信・ディスクを多く使う。必要な測定時だけ実行する。

```bash
python3 research/zkvm-comparison/benchmark.py build-zkvm \
  --no-cache \
  --image-tag csi-zkvm-benchmark:cold \
  --output research/zkvm-comparison/results/build-zkvm-cold.json
```

イメージは測定後も残るため、削除する場合は対象タグを確認してから手動で行う。

## 結果の読み方

JSON の `definition`、`environment`、`input`、`versions` が測定条件、`runs` が生値、
`summary` が min/median/mean/p95/max である。比較の代表値には median を使い、
最低でも入力 shape、CPU、run数、cache条件とともに報告する。

## 4. zkVM 関数別・規模別の長時間計測

profiling版は既存の本番 guest を残したまま、次の段階へ分割している。

| stage | 計測対象 |
|---|---|
| `validate_commitment` | 入力shape検証とSHA-256 commitment照合 |
| `select_subcarriers` | Goertzel SNRによるsubcarrier選択 |
| `bandpass` | 選択subcarrierの移動平均bandpass |
| `pca` | 共分散行列と固定8反復の第1主成分 |
| `vmd` | Goertzelスペクトルと固定12反復の狭帯域分解 |
| `full` | 上記5段階を1つのguest内で連続実行 |

各stageについて以下を記録する。

- guest関数を囲った `cycle_count()` の差
- proofなしのexecutor wall timeとuser cycles
- stage単独のproof wall time、verify wall time
- proof全体のtotal/user/paging/reserved cyclesとsegment数
- request/receiptサイズ

cycle counterは性能分析用のhost提供値であり、その数値自体の真正性を証明するものでは
ない。関数cycleと、stage単独proofの実時間を併記して判断する。

### 工程ごとの独立guest

`full` guestがメモリ不足で最後まで完了しない場合は、既存の本番guestを変更せず、
次の5工程をそれぞれ別のELF/Image IDとして証明できる。

- `validate_commitment`
- `select_subcarriers`
- `bandpass`
- `pca`
- `vmd`

独立guestでは前工程のproof成功を待たない。各工程の直接入力はhostが同じ
`csi-zkvm-core` 関数で準備するため、例えばsubcarrier選択のproofがOOMで失敗しても、
bandpass、PCA、VMDの単独proof測定を継続する。これは性能分離用であり、独立receiptを
連鎖させてパイプライン全体を証明する方式ではない。

```bash
research/zkvm-comparison/run-sweep-in-docker.sh \
  /path/to/measurement.csi \
  --profile-mode isolated \
  --sizes 300x8 \
  --skip-python-circom \
  --output /results/isolated-300x8.json
```

全行列を各工程へ個別に渡す例:

```bash
research/zkvm-comparison/run-sweep-in-docker.sh \
  /path/to/measurement.csi \
  --profile-mode isolated \
  --sizes 4459x4004 \
  --skip-python-circom \
  --output /results/isolated-full.json
```

各工程の結果は完了直後にcheckpoint保存される。失敗レコードにも外側から100ms間隔で
測った `memory.process_peak_rss_bytes` を残す。正常完了時は、proof生成区間だけを
host内部で50ms間隔で測った `profile.proving_memory.peak_rss_bytes` も記録する。
CSVではそれぞれ `process_peak_rss_bytes` と `proving_peak_rss_bytes` で確認できる。
工程コマンド全体のピークとproof区間のピークを混同しないこと。

bandpassには選択済み最大32列、PCAにはフィルタ済み行列、VMDには第1主成分を直接渡す。
そのため `request_input_elements` は元の `samples × subcarriers` より小さくなる場合がある。
hostで依存入力を作る時間は `host_dependency_prepare_seconds` としてproof時間から分離する。

独立guestのproof時間を合計しても本番 `full` proof時間にはならない。各guestで入力展開、
証明初期化、receipt生成の固定費が繰り返されるため、独立値は各工程の単独コストとして
報告する。

最初にprofiling guestを含むzkVMバイナリを更新する。

```bash
docker compose build zkvm-builder
docker compose run --rm zkvm-builder
```

ユーザーが用意したCSIファイルで規模を指定して実行する。タイムアウトはない。

```bash
research/zkvm-comparison/run-sweep-in-docker.sh \
  /path/to/measurement.csi \
  --sizes 64x3,128x4,256x8,512x16,1024x32,2048x32,3000x32 \
  --output /results/scale-sweep.json
```

既定では同じshapeのPython+Circomも測る。zkVMだけにする場合は
`--skip-python-circom` を付ける。sample数とsubcarrier数の影響を分ける例:

```bash
research/zkvm-comparison/run-sweep-in-docker.sh \
  /path/to/measurement.csi \
  --sizes 64x32,128x32,256x32,512x32,1024x32,2048x32,3000x32,512x3,512x8,512x16,512x64,512x128,512x256 \
  --output /results/scale-sweep-wide.json
```

長時間実行はログを残してbackground起動できる。

```bash
nohup research/zkvm-comparison/run-sweep-in-docker.sh \
  /path/to/measurement.csi \
  --output /results/scale-sweep.json \
  > research/zkvm-comparison/results/scale-sweep.log 2>&1 &
```

各stage完了直後にJSONをatomic保存する。同じCSI・同じzkVMバイナリ・同じ
`--output` で再実行すると、完了済みのshape/stageをskipして再開する。

sweep全体のCSI読み込み時間は `timings.csi_read_seconds`、各checkpointでJSON・CSV・
SVG一式を出力した直近の時間は `timings.result_output_seconds` に記録する。累積は
`timings.result_output_seconds_total` で確認できる。

生成物:

- `scale-sweep.json`: 生の測定値、環境、失敗情報
- `scale-sweep.csv`: 集計・論文作図用の平坦化データ
- `scale-sweep-processes.csv`: zkVM内部処理のcycle内訳
- `scale-sweep-system-phases.csv`: Python/Circom/zkVMホスト処理の秒数内訳
- `scale-sweep-proving-seconds.svg`: 規模とproof時間
- `scale-sweep-execution-seconds.svg`: 規模とguest実行時間
- `scale-sweep-function-cycles.svg`: 規模と関数cycle
- `scale-sweep-system-phases.svg`: 規模とシステム各工程の時間
- `scale-sweep-peak-memory.svg`: 独立guestのproof生成区間ピークRSS
