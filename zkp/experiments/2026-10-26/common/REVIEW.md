# 独立レビュー（2026-10-26）

対象: `vmd/model.py`, `vmd/run_sweep.py`, `vmd/diagnostics.py`, `lomb/reference.py`, `lomb/run.py`, `lomb/synthetic.py`, `lomb/supplement.py`。既存Circomソースと共通入力条件に照らした静的レビュー。担当の計算コードは変更していない。

## 報告上の必須区別

1. **LS参照とLS回路は別の比較。** VMD表のLS参照は同一PCA・量子化・128点padding波形へのSciPy高密度探索（0.05–0.99 Hz）。E2E回路LS表は第1アンテナ対の生CSI振幅²・64実時刻点・32周波数bin（0.05–約0.404 Hz）。両表を同一入力での手法優劣として合算しない。
2. **出力の意味も異なる。** VMDの主BPMは全モード・全ビンglobalピーク。LS回路の`bpm`は正常帯域内で強制的に選ぶピークで、正常判定には別の`global_bpm`を使う。特に強い帯域外干渉への誤差は選択規則の差を含む。
3. 共通合成6ケースは同じ元CSIと正解BPMを共有するが、前処理・サンプリング・探索帯域・選択規則までは同じではない。実データは生理的GTなし。実データの平均絶対差・一致率と、合成GTのMAE・正解率を区別する。
4. LSの同一SC浮動小数点参照も**msへ丸めた時刻・同じ64点**を使う。今回のbin差ゼロはこの条件内の結果であり、ns→ms丸めや64点削減の影響ゼロを示さない。
5. K変更には初期中心追加が伴う。配置感度を併記し、8記録を見て選んだ配置の結果は探索的評価とする。未知データでの改善保証や最適化済み精度と呼ばない。

## 算術・選択・GT利用

- 現在の有効入力範囲・実験条件に、整数overflowやtie処理の明らかな不一致は見つからない。LSの大きい積はNumPy `dtype=object` のPython整数。VMDのDFT/係数/二乗和はint64、重み付き中心集計はPython整数。waveform±100と固定128点の範囲内での確認であり、一般入力へ拡張した安全性証明ではない。
- VMDはmode→bin順の最初の最大値、LSは小さいbin/先に選ばれたSCを同点時保持する。既存Circomのstrict `GreaterThan` に対応する。
- SC選択は振幅・GTによらない決定的farthest-point prefix。SC数が増えても同じscaleと既存列を維持している。GTを参照してSCを選ぶ処理は見つからない。
- LSの12bit入力range、timestamp厳密増加、定数列拒否は前処理/回路条件に対応する。参照関数は汎用validatorではなく、任意入力に対するfield wrap/ゼロdeterminantなどを包括検証しているわけではない。今回のデータ範囲に限定した結論にする。

## 時間・小さなメタデータ注意

- VMDの`reference_compute_median_ms`はPython参照計算。回路witnessとGroth16 prove/verifyは別段階。compileは初回1回、witnessとproveの反復数も異なる。共有マシンでの並行作業中の壁時計時間であり、専有環境の処理性能と呼ばない。
- LSの`preparation_seconds`は32SCの共通準備を各countへ再掲した値。SC数ごとの独立前処理時間ではない。`integer_reference_seconds`は基底計算を含まない。witness内時間とNode起動を含むprocess時間は列が分離されている。
- VMD `metadata.json` の共通 `observed_seconds=48`, `padded_samples=32` は実CSI/共通合成CSIに対応するが、直接合成45ケースは64秒128点でpaddingなし。READMEでは区別済み。担当へ条件別メタデータ化を依頼した。

主な研究上の注意は比較対象・入力・出力意味の区別であり、今回の実験結果を無効にする実装上の不一致はこのレビューでは発見していない。
