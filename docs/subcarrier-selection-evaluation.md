# Circom / Python サブキャリア選択の比較

評価専用の Python を追加した。本番入力を Python で選別する処理は追加していない。
現行の Circom 選択回路、証明、チェーン連携、既存 WebUI の動作は変更しない。

今後の評価は実測CSIを基本とする。スクリプトの既定動作も実測のみで、合成データを自動追加しない。
合成評価は過去の結果の再現用に残すが、ユーザーから明示的な依頼がある場合に限って使用する。
以下の合成データの説明と2026-11-09の保存済みレポートは、この方針決定前の実験記録である。

実測結果、図、画面・コードのスクリーンショットは
[2026-11-09 の評価レポート](progress/2026-11-09-selection-comparison/README.md) を参照。
`index.html` はダウンロードしてブラウザーで開ける独立した閲覧用ページ。

## 比較の分離

| 方法 | 入力 | 目的 |
|---|---|---|
| Circom | 本番と同じ整数化済み64点・全候補列 | 実際のコンパイル済み WASM を実行 |
| Python Integer64 | 回路と同じ入力 | 任意精度整数と厳密な有理数比較で計算の一致を確認 |
| Python Float64 | 同じ64行、I/Qを整数化する前 | 整数量子化の影響を確認 |
| Python FloatAll | ミリ秒重複を除いた全行 | 64点への間引きの影響を確認 |
| Python Spectral64 | 回路と同じ整数化済み64点 | 同じ情報量で周期性を重視する選択法と比較 |
| Python SpectralAll | ミリ秒重複を除いた全行 | 全点・浮動小数点で周期性を重視する選択法と比較 |

Integer64 / Float64 / FloatAll は同じ式を使う。

```
P[t] = I[t]^2 + Q[t]^2
S = sum(P)
V = N * sum(P^2) - S^2
D = sum((P[t] - P[t-1])^2)
score = V^2 / ((S^2 + 1) * (V + N*D + 1))
eligible = S >= N*16 and 0 < V <= S^2
```

I/Q はオフセットを除いた値。Float 系も、本番64点から求めた同じ共有スケールを使う。
N は各入力の点数。FloatAll では N や隣接観測点の間隔も変わるため、間引きの影響は
単に計算精度の差ではない。D は時間間隔で正規化しないという現行仕様もそのまま比較する。
同点は列番号が小さい方を選ぶ。`rank: null` は参照方法の適格条件を満たさないことを示す。

Spectral 系は、各列の CSI 電力 `|CSI|²` に
`a*cos(2πft) + b*sin(2πft) + c` を最小二乗で当てはめる。
回路の正常帯域の端点 `(127+29*5)/2540` ～ `(127+29*27)/2540` Hz 内で、
説明分散率が最大の列を選ぶ。適格条件はそれぞれ同じ入力の現行スコアと揃える。
全探索範囲は 0.05 ～ 約0.404 Hz、355点。細かい探索グリッド自体は観測時間による
物理的な周波数分解能を改善しない。

これは今回追加した評価用の Python 参照法であり、既存の FFT/SNR→PCA パイプラインとは異なる。
不均一な実タイムスタンプを使えるため、この比較では Lomb–Scargle を採用した。
バッチ実装の数値結果は [SciPy の floating-mean Lomb–Scargle](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.lombscargle.html)
との一致をテストしている。これは呼吸由来の信号かどうかを保証する検定ではない。

## 精度について言えること

実データは同期した呼吸数・体動ラベルがないため、選択一致率・参照順位・推定周波数差を報告する。
Python の選択を正解と定義しない。Spectral が自身の目的関数で高得点になることも、
実際の呼吸判定精度が高い証拠にはしない。

合成データのみ、既知の呼吸信号を入れた列を正解として正解列選択率を計算する。
各条件4 seed、192点から本番と同じ方法で64点を作る。条件・パラメーターは
`synthetic_cases()` に固定し、結果を見て成功例だけを抽出しない。

- `clean`: 周期信号とガウス雑音。名前に反して無雑音ではなく、呼吸列の振幅90に対して他列の雑音標準偏差120を含む。
- `slow_drift`: 競合列に振幅350・0.025 Hzの大きな低周波変動を加える。
- `in_band_interference`: 競合列に振幅300・0.32 Hzの周期ノイズを加える。周期性だけでは呼吸と識別できない例。

合成評価の周波数誤差は、選ばれた列に**共通の全点 Python LS**をかけた値と既知周波数の差。
選択法を評価するための指標であり、Circom の周波数推定や `isNormal` の精度とは区別する。
回路自身の出力は別に `circuit.frequencyBin / isNormal` として保存する。
この少数の合成条件から実測や臨床での精度を推定しない。

## 再実行

既存の Python 仮想環境、Node.js、PicoScenes パーサー、NumPy、Matplotlib を使う。
テストでは SciPy と pytest も必要。Circom のコンパイル済み WASM と、その隣の
`witness_calculator.js` が必要だが、Groth16 の proving key やウォレットは不要。

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python \
  scripts/evaluate_subcarrier_selection.py sampledata/*.csi \
  --output .local/selection-real-only

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  scripts/test_evaluate_subcarrier_selection.py -q

node scripts/capture_selection_report.cjs .local/selection-real-only
```

別環境では `--manifest` で実測用アーティファクトを指定する。
合成評価は `--include-synthetic` の明示指定がある場合だけ実行し、その場合だけ `--compact-wasm` が必要になる。
既定値は `.local/circom-adaptive-4004/artifacts.json` と
`.local/circom-adaptive/build/csi_lomb_scargle_adaptive_js/csi_lomb_scargle_adaptive.wasm`。
実データは4004候補版、合成データは同じ選択・LSテンプレートの64候補版を使う。
パディングされた候補は選ばれない。実データの候補数は既存パーサーの最頻CSI幅に従う。
列番号はアンテナ組を含むパーサーの0始まり列であり、物理的なtone番号とは限らない。

WASM は manifest のハッシュと照合し、sanity check 有効で witness を計算する。
出力の公開タイムスタンプ・候補数も入力と照合する。
今回の実験は新たな Groth16 証明生成、全 R1CS の独立チェック、チェーン検証を行うものではない。
同じ回路の既存の証明・チェーン検証記録は [前回のレポート](progress/2026-11-09-adaptive-4004/README.md) にある。

ユーザー側の準備は今回不要。実測精度まで評価する次の段階では、CSIと同期した呼吸センサー値、
または収録区間ごとの実測呼吸数・体動ラベルが必要になる。
