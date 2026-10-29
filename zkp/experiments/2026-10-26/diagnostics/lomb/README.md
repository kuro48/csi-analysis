# Lomb–Scargle 公開段階値の診断回路

既存の8サブキャリアE2E回路から独立した`diagnostic.circom`を生成する。既存内部signalへ`<==`で結び付いた **7,325 public outputs** と元の64 public timestamp inputsを持つ。本番回路・既存鍵・既存ベンチマークには変更を加えない。

これはユーザー指定の診断用途で、秘密CSI、中心化波形、基底、投影、周波数スコアを意図的に公開する。通常のプライバシー保護運用に使わない。

## 公開する段階

- 元のcommitment・正常判定・selected SC・帯域peak bin・global peak bin
- signed I/Q、振幅二乗、`64*mag²-sum(mag²)`の中心化波形（各64×8）
- 各SCのsignal energy（8）
- 固定小数sin/cos基底（各32×64、offset除去済、scale1000）
- 各周波数のcos/sin norm、cross norm、Gram determinant
- 各SC/周波数のcos/sin projectionとLS score numerator/denominator（各8×32）
- 各SCの帯域内peak/global peak bin

すべて計算中の既存内部signalからのcopyであり、可視化用Pythonで再計算した値をpublic outputsと呼ぶものではない。復号後の値を独立Python参照と照合する。

`public_schema.json` が名前→public配列offset（0始まり）・shape・signed属性・元signalを定義する。`.sym`のwitness indexがoffset+1と一致することを検査してから実際の`.wtns`公開prefixを取り出す。負数はBN254 scalar fieldの`value > p/2`を`value-p`へ戻す。大きな整数はJSON decimal stringで保持する。

## 実データ

代表入力は`../../lomb/inputs/csi_20260526_034004_w0_sc8.json`。本編で使用したRaw収録冒頭48秒の同じ64観測点、同じTx0/Rx0、同じ8 SC、同じ整数I/Qとms時刻を使う。`input.json`へそのままコピーし、元入力SHA256を記録する。

実際に選ばれたSCを`selectedSubcarrier`から取得し、`selection.json`に元tone indexへの対応を記録する。SC0を選択SCと見なす処理はしない。

## 再現と出力

```sh
# source/schema生成のみ（default）
python3 zkp/experiments/2026-10-26/diagnostics/lomb/run_debug.py
# 大型proof計時との競合を避け、CPU空き確認後
python3 zkp/experiments/2026-10-26/diagnostics/lomb/run_debug.py --compile --witness
# 診断用に独立setup/contribution/prove/verify。実測では既存ptau21を使用
python3 zkp/experiments/2026-10-26/diagnostics/lomb/run_debug.py --prove --ptau zkp/experiments/2026-10-26/.cache/ppot_0080_21.ptau
```

- `decoded_public.json`：実際のpublic値を元のshapeと符号へ戻した値。`proof_verified`でwitness取得と証明検証済みを区別。
- `public_from_witness.json`：実witnessから取り出した公開配列。prove後の`public.json`と全値完全一致を検査。
- `selected_waveform.csv`：実selected SCのI/Q→振幅²→中心化と、選択binのsin/cos基底。
- `selected_spectrum.csv` / `spectra_all_sc.csv`：公開整数projection/numerator/denominatorと描画用ratio。
- `normalized_score_display_only`は**回路外**でnumerator/denominatorを浮動小数点除算した表示値。回路は除算せず交差積でargmaxを決める。
- `centered_display_divide64`も描画用の**回路外**スケール変換。公開された正確な整数を同じCSVに保持。
- `validation.json`：全段階のPython参照一致、全SC peak、元4推定出力、schema index整合。
- `proof_metrics.json` / `verify.log`：実診断Groth16証明の検証結果。診断は公開値が増えるため、本編非公開回路の性能値と置き換えない。
- `tamper_validation.json` / `verify_tampered.log`：証明を固定し、公開`debugMagnitudeSquared[0][0]`だけを+1した`public_tampered.json`が明示的にinvalid proofとして拒否される負例検査。元の`public.json`は変更しない。中間値も証明に拘束されることを確認する。

実行結果: compile/witness完了、総562,273制約（非線形561,760、線形513）。7,325公開出力のうちcommitmentを除く7,324値が独立整数参照と一致した。選択されたSCはlocal7（元tone32）、帯域/globalピークはともにbin10（約9.8504 BPM）。compile 38.887秒、Node起動・WASM読込・witness書込を含むwitness process 0.495秒。Groth16証明も生成・検証済みで、`decoded_public.json`の`proof_verified`はtrue。`public.json`の全7,389値がwitness公開prefixと完全一致した。

## Groth16証明・改ざん拒否の実測

独立診断回路・新規contribution・ptau21で、setup 139.616秒、contribution 41.477秒、prove 9.905秒、verify 0.266秒（各1回）。これらは公開出力が増えた診断回路の計時であり、本編の非公開SC8回路・3回中央値とは区別する。全562,273制約の`wtns check`もPASS。

元proofと公開配列はverify `OK!`。同じproofのまま公開配列offset1029の`debugMagnitudeSquared[0][0]`を1,164,708→1,164,709へ変更した負例は、returncode1・`Invalid proof`として拒否された。したがって、この公開中間値も証明の検証対象に拘束されている。改ざんされた値は別ファイルに保存し、正規の公開配列や図の入力は変更していない。
