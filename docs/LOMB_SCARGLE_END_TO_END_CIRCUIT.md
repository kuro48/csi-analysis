# 生CSI入力 Lomb--Scargle 完全回路化プロトタイプ

`zkp/circuits/csi_lomb_scargle_end_to_end.circom` は、既存の
`csi_lomb_scargle_normality.circom` を変更せずに追加した独立回路である。

## 証明範囲

秘密のCSI I/Q値から次の処理をすべて回路内で拘束する。

1. 12-bit符号化I/Q値の範囲検査
2. 全I/Q値のsalt付きPoseidonコミットメント
3. `I^2 + Q^2` による振幅二乗
4. 除算を使わない厳密な平均除去
5. 公開タイムスタンプからのsin/cos基底生成
6. Gram行列形式の正規化Lomb--Scargleスコア
7. 正常帯域ピークが最大のサブキャリア選択
8. 選択サブキャリアの全探索帯域argmax
9. グローバルピークの6--22 BPM判定

CSI値、振幅、中心化波形、周波数投影、スペクトルは公開しない。

## 固定パラメータ

| 項目 | 値 |
|---|---:|
| サンプル数 | 64 |
| サブキャリア数 | 8 |
| 周波数bin数 | 32 |
| 周波数グリッド | `(127 + 29*bin) / 2540 Hz` |
| 正常bin | 5..27（約6.43..21.50 BPM） |
| I/Q符号化 | 12-bit、offset 2048 |
| タイムスタンプ | 24-bit相対ms、厳密単調増加 |

これは制約数と証明時間を測るためのfeasibilityサイズである。現行の384サンプル・
128周波数binへ直ちに拡大すると、エッジ端末でのGroth16証明生成は非実用的になる
可能性が高い。そのため、まず本回路で精度・制約数・メモリ・証明時間を測定する。

## 現行アルゴリズムとの差異

本回路はPCA後の波形を入力とせず、生CSIから直接サブキャリアごとの
Lomb--Scargleスコアを計算する。したがって「生CSIから結果まで切れ目なく証明する」
一方で、現行PythonパイプラインのSNR上位256選択、Butterworthフィルタ、PCAは再現しない。
これは浮動小数点PCAを回路外に残さないための、回路親和的な推定器である。

平方根を含む絶対値の代わりに振幅二乗を使う。定常成分を持つCSIでは、呼吸による
振幅変調の基本周波数を維持しながら平方根制約を避けられる。

## 公開値と運用

- `timestampsMs`
- `csiCommitment`
- `isNormal`
- `selectedSubcarrier`
- `estimatedFrequencyBin`
- `globalPeakFrequencyBin`

`commitmentNonce` は秘密に保つ。エッジデバイスは公開された `csiCommitment`、
タイムスタンプ範囲、デバイスID、回路バージョンへ署名することで、証明を特定の
キャプチャへ結び付けられる。

## 単体テスト

既存の `package.json` を変更しないため、専用テストを直接実行する。

```bash
cd zkp
npx mocha test/lomb_scargle_end_to_end.test.js
```

回路だけをコンパイルする場合:

```bash
cd zkp
mkdir -p build/end_to_end
circom circuits/csi_lomb_scargle_end_to_end.circom \
  --O1 --r1cs --wasm --sym -o build/end_to_end -l node_modules
```
