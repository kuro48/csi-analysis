# VMD 各処理値の公開出力版（診断専用）

既定K3/R4の現行回路を別名 `vmd_k3_r4_public_trace.circom` に複製し、内部値を `<==` で公開出力へ接続する。通常回路・通常鍵・既存の比較時間は変更しない。診断用のため、元の秘密波形と内部係数が公開される。nonceは秘密入力のまま。

公開出力は1785個、公開入力parentCommitmentを含むpublicSignalsは1786個。元の4出力を先頭に保ち、以下を追加する。

| 配列 | 要素数 | 接続元 |
|---|---:|---|
| debugWaveform[128] | 128 | waveform |
| debugDftReal[63] | 63 | fc |
| debugDftImag[63] | 63 | fs |
| debugModeReal[4][3][63] | 756 | ur |
| debugModeImag[4][3][63] | 756 | ui |
| debugCenters[5][3] | 15 | center（初期+各反復後） |

`public_schema.json` に配列形状・publicSignalsの0開始index区間・witnessの1開始index・実内部信号名を記録。配列は右側のindexが最速で変わるrow-major。符号付き値はBN254有限体から中央表現へ復号する。hash/parentCommitmentは符号付きと解釈しない。

代表入力は `common/windows/csi_20260526_034004_w0.npz`。実観測48秒を2Hz96点へ変換した後にゼロ32点を追加した128点である。

## 出力の区別

- `public.json`: 実際の回路witnessから抽出したcanonical decimal-string配列。公開値の原本。
- `reference_for_validation.json`: 照合のためのPython再計算。**公開値の代わりに表示・証明するものではない**。
- `witness_validation.json`: 公開index、実内部信号、独立参照の照合記録。witness生成とR1CS検査の結果。
- `trace.json`: `public.json`のみを復号して得た表示用データ。入力、DFT、全反復・全モードのスペクトル、中心軌跡を含む。
- `proof.json`/`proof_public.json`/`verification_key.json`/`proof_validation.json`: `prove`実施後のみ生成される本物のGroth16証明・検証結果。witness検証だけで証明済みとは扱わない。

## 波形表示の意味

回路内部には周波数係数が存在し、モードの時間波形は存在しない。`trace.json` の `waveform_inverse_dft_off_circuit` は公開係数を **回路外で逆DFTした描画変換**。`complex=(real-1j*positive_sine)/1000` をrfft bin1..63へ置き、DC/Nyquistを0にして `irfft(n=128)` する。回路は+sin係数を計算するので、通常のFFT複素数は虚部の符号を反転する。

power、モードの和、入力との差(residual)も回路外の表示計算であり、追加の証明対象出力ではない。DC/Nyquist省略、三角表丸め、近似VMDの再構成保証なしのため、逆DFT波形を入力の完全再現とは解釈しない。縦軸は正規化整数振幅で、物理的な呼吸振幅ではない。

## 実行

比較計時と競合しない時間帯にstageを順番に実行する。ソース生成だけの `generate_debug.py` はcompile/proofを開始しない。

```bash
python3 research/2026-10-26/diagnostics/vmd/run_diagnostic.py prepare
python3 research/2026-10-26/diagnostics/vmd/run_diagnostic.py compile
python3 research/2026-10-26/diagnostics/vmd/run_diagnostic.py witness
python3 research/2026-10-26/diagnostics/vmd/run_diagnostic.py prove
```

prepareは既存input.jsonがあればnonceを再生成せず同じ入力を保存する。compileは実制約数と公開信号数からptau19容量を確認する。proveは通常鍵を再利用せず専用のローカル診断鍵を新規作成し、証明public値と表示public値の完全一致、正常検証、公開波形の1要素改変に対する検証拒否を確認する。ローカル診断鍵は本番trusted setupとして使用しない。

source/schema作成時点の見込みは通常約340734制約+公開信号1786で2^19未満。実際の値と所要時間はcompile.json/proof_validation.jsonの測定値を採用する。

## 代表Raw入力での実行結果

prepare/compile/witness実行済み。制約数340,737、publicSignals1,786でptau19容量内。出力43.125 BPM、選択mode index2。中心軌跡は `[8,24,48] → [8,24,47] → [8,24,46] → [8,24,46] → [8,24,46]`。

publicのschema順序1,786要素、独立整数参照1,785要素（hashを除く）が一致し、snarkjsのR1CS witness checkも成功した。最適化により1,781個の元内部名はSYM上で消去されているため、元内部名の直接witness比較は5件に限定される。コピー出力は回路ソースで実内部へ接続され、実際の公開値・独立参照・R1CS制約を照合している。

compile4.556秒、witness計算0.267秒。witness生成＋R1CS検査＋表示JSON書き出し全stageは3.77秒。最大RSSはcompile約466 MiB、witness stage約1.10 GiB。`resource_usage.json`にstage計測値を保存。通常32SC回路のsetupと並行した診断値で、通常回路のベンチマーク値へ混ぜない。

Groth16証明生成・正常検証まで完了し、`proof_validation.json`に結果を保存した。証明に含まれる1,786個の公開値と表示原本public.jsonの完全一致を確認。公開波形の1要素、DFT実部の1要素、モード実部の1要素、中心の1要素をそれぞれ変更すると同じ証明は検証拒否された（`intermediate_tamper_validation.json`）。

| 工程 | 実測秒 |
|---|---:|
| Groth16 setup | 20.212 |
| 専用鍵へのlocal contribution | 22.621 |
| proof生成 | 4.282 |
| 正常verify | 0.197 |

setup/contribution/prove/verifyの全stageは47.90秒、最大RSSは5,399,740,416 bytes（約5.03 GiB）。これは公開出力を追加した**診断回路専用**の測定で、通常VMDの処理時間ではない。初期setup/contributionと毎回のproof生成時間を区別する。

Groth16が検証するのは公開した整数内部値と回路制約の整合性であり、描画用の逆DFTを回路内で実行・証明したわけではない。
