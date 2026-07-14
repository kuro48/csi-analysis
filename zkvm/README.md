# CSI 5-1 RISC Zero pipeline

`5-1.ipynb` の数値解析を RISC Zero guest 内で再実行する実験系です。
PicoScenes 容器のパースだけは Python ホストで行い、振幅行列以降の
SNRサブキャリア選択、帯域抽出、PCA、VMD互換の反復狭帯域分解、
ピーク呼吸数判定を guest 内で実行します。

## 重要な互換性メモ

zkVM では実行を完全に決定的にするため、Python/SciPy/scikit-learn/vmdpy と
同じライブラリ実装は使いません。`5-1-fixed-v1` は同じ処理段階と
同じ 6–22 bpm 判定を持つ固定アルゴリズム版です。Python 版との
数値完全一致ではなく、2系統の出力差を研究評価する前提です。

## ビルド

RISC Zero 3.0.5（現行の crates.io 安定版）の toolchain を入れた後に実行します。

```bash
rzup install
cd zkvm
cargo test -p csi-zkvm-core
cargo build --release -p csi-zkvm-host
```

Backend は既定で `zkvm/target/release/csi-zkvm-host` を使います。
別パスの場合は `CSI_ZKVM_BINARY` を設定してください。
