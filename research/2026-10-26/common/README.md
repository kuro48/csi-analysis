# 共通実験データ（2026-10-26）

Raw の10個の `.csi` を実際に解析し、各ファイル冒頭48秒から比較用入力を作成した。原本は変更していない。`manifest.json` は原本SHA256、CSI幅別フレーム件数、最頻幅、時刻品質、PCA選択を記録する。`data_quality.csv` は報告向けの一覧。

## 最初に確認すべき制約

- **呼吸数の同時計測正解値はRaw内で見つからなかった。** 実データの手法間BPM差は一致度であり、生体呼吸数に対する精度ではない。`kokyu` / `daremoinai` はファイル名に基づく定性的な区別に過ぎず、正常/異常の確定ラベルにしない。
- 直下8記録の実測長は53.22–59.52秒。`sample_data` の2記録も60.97 / 63.03秒で、**64秒の実測窓は1つもない**。主条件を48秒に固定した。
- 最頻幅を採用した後の実効平均レートは2.51–78.22 Hz。既存パイプラインの100 Hz仮定をそのまま適用するとBPM換算とフィルタが変わるため、この研究入力は実時刻を利用して100 Hzへ補間した。これは本番前処理を変更したという意味ではない。
- 幅980は245 tones × 2 Tx × 2 Rx、幅8100は2025 × 2 × 2である。配列幅を物理サブキャリア本数と同一視しない。LSの物理本数比較では第1 Tx/Rx対の最初の `numTones` 列に固定する。
- 最頻幅のみ採用しているため、異なるPacketFormat/幅のフレームは除外される。古い記録では53列のlegacyフレームが選ばれる場合もある。今回の8/10記録を同一計測条件の独立被験者とみなせない。

## 入力生成

1. 既存 `load_csi_matrix_with_timestamps` でCSIと`systemns`を同時取得。安定ソート、同時刻の重複を除去。
2. LSへは冒頭 `[0,48)` 秒の複素CSIと記録時刻を渡す。サンプル・列の選択はLS実験コードに記録。
3. VMDへは振幅 `abs(CSI)` を時刻に従って100 Hzの4800点に線形補間。複素位相を補間してから絶対値を取る処理はしない。**48秒境界での線形補間には、全記録中の次の実測点を端点として使う場合がある**（窓外フレームを呼吸解析対象に追加するものではないが、LSの厳密な入力集合とは境界で異なる）。
4. 既存SNR選択（最大256列）、既存0.1–1 Hz Butterworth、3成分PCA、既存PC選択。PCAは再現性のためfull SVD。
5. `resample_poly(1,50)` で2 Hz・96点。既存近似VMD入力関数の規則に合わせ、32点ゼロ埋め→平均除去→最大絶対値100に整数化し128点へ。**末尾16秒は観測ではない。** padding感度のため未padding96点も保存。

`windows/*.npz` の仕様:

| key | 内容 |
|---|---|
| `csi_complex` | `[raw time, flattened CSI column]` 複素CSI |
| `timestamps_ns`, `time_seconds` | 同じ行の絶対ns、開始基準秒 |
| `signal128` | ±100 int64、回路秘密入力 |
| `waveform128` | 96点+zero32点、平均除去済みfloat |
| `waveform96` | resample後の未padding波形 |
| `pc100`, `pcs100` | 100 Hzの選択PCと全3PC |
| `selected_indices`, `snr` | 既存SNRによる列選択の記録 |
| `times128` | 2 Hzの128点時刻（末尾32点はpadding） |

## 既知周波数の共通対照

`synthetic/*.npz` はseed20261026、9/12/18 BPM × ノイズ標準偏差0.02/0.15の6条件。32サブキャリアで、`CSI_j(t) = [10 + gain_j sin(2π f t) + Gaussian noise] exp(i phase_j)`、gainは0.6–1.4。100 Hz・48秒のCSIから、実データと同じVMD前処理入力を生成した。`target_bpm` が既知正解値。LSも同じCSIを使える。合成データ精度と生体精度を区別する。

## サブキャリア配列順の根拠

インストール済みPicoScenes Pythonパーサはcommit `f676855accedf79e848bf2f1d10ee5c1f649a33a`。[`parse_CSI` の実装](https://github.com/wifisensing/PicoScenes-Python-Toolbox/blob/f676855accedf79e848bf2f1d10ee5c1f649a33a/picoscenes.pyx#L475-L494)は `CSIArray.array` をそのまま返す。

ローカル `Code/PicoScenes-MATLAB-Toolbox-Core/rxs_parsing_core/CSISegment.cxx`（core commit `75b099d9841e539e8c3c50151e1442b5f4bd5382`）L175は `dimensions={numTonesFinal,numSTS,numRx,1}`、`ColumnMajor` と定義する。よってtoneが最速で、先頭`numTones`は第1アンテナ対。GitHub tree APIでインストール済みPythonラッパcommitの`rxs_parsing_core`サブモジュールSHAを確認し、ローカルcoreと完全一致した（取得結果は`parser_tree.json`）。したがって解析に使ったパーサと同じcore実装を根拠としている。

## 再現

```sh
# numpy, scipy, scikit-learn, picoscenesを持つ環境
PY=/Users/ryunosukekurokawa/Research/WiFi-CSI-Privacy/Presentations/IA/ieicej3.4a/.csi-figures/venv/bin/python
OPENBLAS_NUM_THREADS=1 "$PY" research/2026-10-26/common/prepare_data.py
OPENBLAS_NUM_THREADS=1 "$PY" research/2026-10-26/common/prepare_synthetic.py
python3 research/2026-10-26/common/validate_data.py
```

`validation.json` に10実窓/6合成窓の有限値・時刻単調・整合・整数化・原本SHA256などのPASSを保存。PCAP1件はこのPicoScenes処理の対象外として`manifest.excluded`に記録した。生成NPZは約548 MBで、再現可能なローカル実験アセットである。
