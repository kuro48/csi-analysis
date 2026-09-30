# Lomb–Scargle完全回路化プロトタイプ 処理解説

対象回路: `zkp/circuits/csi_lomb_scargle_end_to_end.circom`

## 1. 概要

この回路は、秘密のCSI I/Q値を入力として、振幅抽出、Lomb–Scargle周波数解析、
サブキャリア選択、呼吸周波数推定、正常帯域判定までを回路内で実行する。

```text
秘密CSI I/Q
  ↓
入力範囲検査・Poseidonコミットメント
  ↓
振幅二乗 I²+Q²
  ↓
平均除去
  ↓
公開タイムスタンプからsin/cos基底生成
  ↓
Lomb–Scargleスコア計算
  ↓
正常帯域ピーク探索
  ↓
最良サブキャリア選択
  ↓
全帯域ピーク探索
  ↓
BPM帯域判定
```

CSI値、振幅波形、中心化波形、周波数射影、スペクトルは公開しない。

## 2. 固定パラメータ

現在の回路は実行可能性を評価するための固定サイズである。

| 項目 | 値 |
|---|---:|
| サンプル数 | 64 |
| サブキャリア数 | 8 |
| 周波数bin数 | 32 |
| I/Q符号化 | 12-bit、offset 2048 |
| タイムスタンプ | 24-bit相対ミリ秒 |
| 正常帯域bin | 5～27 |
| 正常帯域 | 約6.43～21.50 BPM |

周波数bin `k` は次の周波数に対応する。

```text
frequencyHz(k) = (127 + 29k) / 2540
BPM(k)         = 60 × frequencyHz(k)
```

例えばbin 18は約0.2555 Hz、約15.33 BPMである。

## 3. 秘密入力と公開情報

### 秘密入力

```circom
signal input csiI[SAMPLE_COUNT][SUBCARRIERS];
signal input csiQ[SAMPLE_COUNT][SUBCARRIERS];
signal input commitmentNonce;
```

- `csiI`: CSIの実部
- `csiQ`: CSIの虚部
- `commitmentNonce`: CSIコミットメントをsaltする秘密値

### 公開入力

```circom
signal input timestampsMs[SAMPLE_COUNT];
```

`main` で `public [timestampsMs]` と指定しているため、相対タイムスタンプだけが公開入力になる。

### 公開出力

```circom
signal output csiCommitment;
signal output isNormal;
signal output selectedSubcarrier;
signal output estimatedFrequencyBin;
signal output globalPeakFrequencyBin;
```

| 出力 | 意味 |
|---|---|
| `csiCommitment` | 全秘密I/Q値を拘束するPoseidonコミットメント |
| `selectedSubcarrier` | 正常帯域スコアが最大のサブキャリア |
| `estimatedFrequencyBin` | 選択サブキャリアの正常帯域内ピーク |
| `globalPeakFrequencyBin` | 選択サブキャリアの全探索帯域ピーク |
| `isNormal` | グローバルピークが正常帯域なら1 |

## 4. 処理1: タイムスタンプ検査

先頭タイムスタンプが0であることを強制する。

```circom
timestampsMs[0] === 0;
```

すべてのタイムスタンプを `Num2Bits(24)` で24-bit範囲に制限する。

```text
0 ≤ timestamp < 2²⁴ ms
```

さらに隣接時刻について次を強制する。

```text
timestampsMs[i-1] < timestampsMs[i]
```

これにより、逆転、重複、範囲外の時刻を拒否する。不均一な間隔はLomb–Scargleの
対象なので許可される。

## 5. 処理2: sin/cos基底生成

公開タイムスタンプから各周波数binの次の基底を回路内で生成する。

```text
cos(2π fₖ tᵢ)
sin(2π fₖ tᵢ)
```

浮動小数点の三角関数は使用しない。象限縮約と固定小数点Taylor近似を利用する。
周波数方向へ複素回転を連続適用すると丸め誤差が蓄積するため、16 binごとに
タイムスタンプから基底を直接再計算し、アンカー間だけ複素回転する。

## 6. 処理3: I/Q入力の範囲検査

符号付きI/Q値は、2048のオフセットを加えた非負整数として入力する。

```text
encoded = signedValue + 2048
```

例:

```text
signed I = -100
encoded  = 1948
```

`Num2Bits(12)` により次の範囲へ制限する。

```text
0 ≤ encoded I/Q < 4096
```

オフセットを戻した値は、おおむね `-2048..2047` になる。

## 7. 処理4: CSIのPoseidonコミットメント

秘密nonceを初期状態として、全I/Q値をサンプル優先、サブキャリア優先の固定順序で
Poseidonハッシュチェーンへ入れる。

```text
state₀ = commitmentNonce
state₁ = Poseidon(state₀, I[0][0], Q[0][0])
state₂ = Poseidon(state₁, I[0][1], Q[0][1])
...
state₅₁₂ = Poseidon(state₅₁₁, I[63][7], Q[63][7])
```

最終状態を `csiCommitment` として公開する。CSIを1値でも変えるとコミットメントも変わる。
nonceを秘密にすることで、小さな合成データに対する単純な辞書攻撃を難しくする。

タイムスタンプはコミットメントには含めないが、Groth16の公開入力として証明に拘束される。

## 8. 処理5: 符号付きI/Qへの復号

入力からオフセットを引く。

```text
Iᵢ,ₛ = csiIᵢ,ₛ - 2048
Qᵢ,ₛ = csiQᵢ,ₛ - 2048
```

`i` はサンプル、`s` はサブキャリアを表す。

## 9. 処理6: 振幅二乗

通常のCSI振幅は次である。

```text
|CSI| = sqrt(I² + Q²)
```

平方根は回路コストが高いため、本回路では次の振幅二乗を使用する。

```text
mᵢ,ₛ = Iᵢ,ₛ² + Qᵢ,ₛ²
```

これにより平方根witness、除算、追加の固定小数点誤差を避ける。ただし、現行Pythonの
`np.abs(CSI)` と数値的に同一の波形ではない。

## 10. 処理7: 平均除去

サブキャリアごとに振幅二乗の合計を求める。

```text
Mₛ = Σᵢ mᵢ,ₛ
```

通常の平均除去は次である。

```text
mᵢ,ₛ - Mₛ/N
```

回路内の除算を避けるため、次の等価なスケーリングを行う。

```text
yᵢ,ₛ = N × mᵢ,ₛ - Mₛ
      = N × (mᵢ,ₛ - mean(mₛ))
```

全サンプルへ同じ倍率 `N` が掛かるだけなので、信号エネルギーで正規化する
Lomb–Scargleスコアには影響しない。

## 11. 処理8: 信号エネルギー

各サブキャリアについて、中心化信号のエネルギーを求める。

```text
YYₛ = Σᵢ yᵢ,ₛ²
```

`IsZero` により `YYₛ != 0` を強制する。全サンプルが一定で情報を持たないサブキャリアや、
後段の正規化分母が0になる入力は拒否される。

## 12. 処理9: sin/cos基底のGram行列

不均一サンプリングではsin基底とcos基底が完全には直交しない。各周波数binについて
次を計算する。

```text
CC_f = Σᵢ cos²(2πftᵢ)
SS_f = Σᵢ sin²(2πftᵢ)
CS_f = Σᵢ cos(2πftᵢ)sin(2πftᵢ)
```

Gram行列の行列式は次である。

```text
det_f = CC_f × SS_f - CS_f²
```

`det_f != 0` を強制し、sin/cos基底が独立でない入力を拒否する。

## 13. 処理10: 波形のsin/cos射影

各サブキャリア `s`、各周波数 `f` について次を求める。

```text
Cₛ,f = Σᵢ yᵢ,ₛ cos(2πftᵢ)
Sₛ,f = Σᵢ yᵢ,ₛ sin(2πftᵢ)
```

この値が大きいほど、その周波数成分が波形に強く含まれる。

## 14. 処理11: 正規化Lomb–Scargleスコア

τを明示的に計算せず、Gram行列を使う代数的に等価な形式を用いる。

分子:

```text
Numeratorₛ,f =
    SS_f × Cₛ,f²
  - 2 × CS_f × Cₛ,f × Sₛ,f
  + CC_f × Sₛ,f²
```

分母:

```text
Denominatorₛ,f =
    (CC_f × SS_f - CS_f²) × YYₛ
```

スコア:

```text
Pₛ,f = Numeratorₛ,f / Denominatorₛ,f
```

回路内では実際の除算を行わず、分子と分母を別々に保持する。

## 15. 処理12: 正常帯域内のピーク探索

各サブキャリアについてbin 5～27を探索し、正常帯域内の最大スコアを求める。

2つの分数、

```text
Nₐ/Dₐ と Nᵦ/Dᵦ
```

を比較するときは除算せず、次を比較する。

```text
Nₐ × Dᵦ > Nᵦ × Dₐ
```

この交差乗算によって、各サブキャリアの正常帯域内最大スコアとbinを求める。

## 16. 処理13: サブキャリア選択

8本のサブキャリアについて、正常帯域内最大スコアを交差乗算で比較する。

```text
selectedSubcarrier =
    argmaxₛ max_{f in normal band} Pₛ,f
```

これは現行PythonのSNR上位256選択、バンドパス、PCA、呼吸成分選択をそのまま再現する
処理ではない。浮動小数点PCAを回路外に残さず、生CSIから直接推定するための
回路親和的なサブキャリア選択である。

## 17. 処理14: 全探索帯域のピーク探索

正常帯域だけで最大値を探すと、結果は必ず正常帯域になる。そのため、正常判定には
全32binを対象としたグローバルピークを使用する。

各サブキャリアについて、

```text
globalPeakₛ = argmax_{f in all bins} Pₛ,f
```

を求める。その後、選択されたサブキャリアの結果だけをone-hot形式で抽出する。

## 18. 処理15: 2種類の周波数bin出力

回路は2種類のbinを出力する。

### `estimatedFrequencyBin`

選択サブキャリアの正常帯域内ピーク。呼吸数表示に使用できる。

### `globalPeakFrequencyBin`

選択サブキャリアの全帯域ピーク。正常・異常判定に使用する。

例えば0.4 Hz付近が支配的なら、正常帯域内にも小さな最大値は存在するが、
`globalPeakFrequencyBin` は0.4 Hz付近になる。

## 19. 処理16: 正常判定

グローバルピークが正常bin範囲に入っている場合だけ `isNormal=1` とする。

```text
isNormal =
    (globalPeakFrequencyBin >= 5)
    AND
    (globalPeakFrequencyBin <= 27)
```

正常帯域内ピークではなくグローバルピークを使うことで、「正常帯域内からピークを
選んだから必ず正常になる」という循環判定を避ける。

## 20. 秘密のまま維持される値

- CSI I/Q値
- commitment nonce
- 振幅二乗
- 中心化したサブキャリア波形
- 信号エネルギー
- sin/cos射影値
- 各周波数のLomb–Scargleスコア
- スペクトル全体

## 21. 現時点の完全回路化範囲

回路化されている範囲は次である。

```text
固定形式CSI I/Q
→ 振幅二乗
→ 平均除去
→ Lomb–Scargle
→ サブキャリア選択
→ 呼吸周波数推定
→ 正常判定
```

次は含まれない。

- PicoScenes `.csi` バイナリの解析
- 現行PythonのFFT/SNR上位256選択
- Butterworthバンドパス
- PCA
- 384サンプル、128周波数binの本番サイズ

したがって、「現行Pythonパイプラインを数値的にそのまま再現した回路」ではない。
「固定形式の生CSIから直接Lomb–Scargle呼吸推定を行う、回路向けアルゴリズム」を
end-to-endで制約したプロトタイプである。

## 22. 検証済み項目

- Circomコンパイル成功
- witness生成成功
- 正常呼吸0.25 Hzの推定成功
- 帯域外ピークの異常判定成功
- 非単調タイムスタンプの拒否成功
- 制約数: 807,453
  - 非線形制約: 570,079
  - 線形制約: 237,374
- 秘密入力: 1,025
- 公開入力: 64
- 公開出力: 5

Groth16のTrusted Setupとproof生成は未実施である。この制約数では、少なくとも
2^20規模のPowers of Tauが必要になる。
