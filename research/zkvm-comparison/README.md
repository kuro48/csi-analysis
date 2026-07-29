# zkVM / Python + Circom 時間計測

実CSIファイルを1回処理し、各工程にかかった時間をJSONへ保存する。
run数、warm-up、入力サイズ、stage、グラフ生成などの追加オプションは持たない。

## 全体比較

Python解析 + Circomと、zkVMの処理を1回ずつ実行する。

```bash
research/zkvm-comparison/run-execution-in-docker.sh \
  ./measurement.csi \
  ./research/zkvm-comparison/results/execution.json
```

記録する主な時間:

- `csi_read_seconds`: CSIの読み込みと行列化
- `python_circom.timings.python_analysis_seconds`: Pythonによる呼吸解析
- `python_circom.timings.python_processes`: Python解析内部の工程別時間
- `python_circom.timings.circom_witness_seconds`: witness生成
- `python_circom.timings.circom_prove_seconds`: Groth16証明生成
- `python_circom.timings.circom_verify_seconds`: Groth16検証
- `zkvm.timings.input_prepare_seconds`: 固定小数点入力の作成
- `zkvm.timings.input_json_write_seconds`: JSON入力の書き込み
- `zkvm.timings.prove_and_verify_seconds`: zkVM証明生成とreceipt検証

どちらかが失敗しても、成功した側の時間と失敗内容をJSONへ保存する。

## zkVM工程別

zkVMの固定された各工程を1回ずつ計測する。

```bash
research/zkvm-comparison/run-sweep-in-docker.sh \
  ./measurement.csi \
  ./research/zkvm-comparison/results/stages.json
```

計測する工程:

- `validate_commitment`
- `select_subcarriers`
- `bandpass`
- `pca`
- `vmd`
- `full`

各工程について次の時間を記録する。

- `outer_seconds`: コマンド全体
- `guest_execution_seconds`: 証明なしのguest実行
- `prove_seconds`: 証明生成
- `verify_seconds`: receipt検証

## Pythonから直接実行

Docker内など、依存関係とzkVMバイナリが利用できる環境では直接実行できる。

```bash
python research/zkvm-comparison/benchmark.py \
  --csi-file ./measurement.csi \
  --output ./execution.json

python research/zkvm-comparison/sweep.py \
  --csi-file ./measurement.csi \
  --output ./stages.json
```

どちらのスクリプトも入力CSI全体を処理する。結果JSONは
`research/zkvm-comparison/results/` 配下ではGit管理対象外となる。

Python + CircomとzkVMは保証する処理内容が異なるため、結果は同一アルゴリズムの
実装速度差ではなく、現在の2方式の処理コストとして扱う。
