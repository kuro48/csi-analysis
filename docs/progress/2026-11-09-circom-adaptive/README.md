# Circom内サブキャリア選択の実装・検証記録

仕様・コード抜粋・再現手順・今後必要な作業は[実装説明](../../circom-adaptive-selection.md)を参照。
Pythonでの候補評価は行わず、Circom内で全候補を採点・比較して1本を選び、LS判定へ接続した。
WebUIの変更はなく、この記録は回路コードと検証結果を対象にする。

## 検証環境

- Intel Core i5-8500B 3.00GHz / 16GiB RAM / macOS
- Circom 2.2.3、Node.js 26.3.1、snarkjs 0.7.5
- 合成CSI、64時刻×64候補、13番目（ゼロ起点）の候補に0.25Hzの振幅変動
- R1CS: 625,867制約、596,947 wires、秘密入力8,193、公開入力65、公開出力5
- 公開Phase 1ファイルはsnarkjs公式掲載のBLAKE2b-512と一致することを確認

## 回路テスト

計18テストが成功した。

| 対象 | 件数 | 主な確認内容 |
|---|---:|---|
| 入力整形 | 3 | 全列保持、パディング、4,004列の黙った間引きの拒否、入力不整合 |
| 選択回路 | 8 | スパイク除外、同点、Qのみの変動、符号境界、滑らかさ、整数参照との一致、全列コミット、内部witness改ざん |
| 新LS接続 | 4 | 等間隔8本で欠落する13番候補、帯域外判定、53候補＋パディング、時刻異常 |
| 旧LS回帰 | 3 | 正常帯域、帯域外、時刻異常 |

frontendの `npm run lint` / `npm run type-check` も成功。
旧回路のテンプレート切り出し前後でR1CSのSHA-256は完全一致した:

```text
dc7b3c8cfbeb242be9690e4e5cd0fba930be36a61332975cc4b48556ac7a9f1d
```

## Groth16証明

[report.json](report.json) に実測時間・判定結果・公開信号改ざんの検証結果を保存した。
[proof.json](proof.json)、[public.json](public.json)、[verification_key.json](verification_key.json)
は同じ実行から得た検証用の公開成果物。ローカルで次のコマンドで再検証できる。

```sh
node zkp/node_modules/snarkjs/build/cli.cjs groth16 verify \
  docs/progress/2026-11-09-circom-adaptive/verification_key.json \
  docs/progress/2026-11-09-circom-adaptive/public.json \
  docs/progress/2026-11-09-circom-adaptive/proof.json
```

計測はこの環境での1回の試行であり、統計的な性能評価ではない。
合成データでの回路・証明の成立を確認したもので、実測CSIでの判定精度を示さない。
4,004列版、WebUI/APIとの接続、Sepolia/Fabric上の新版Verifierによる検証は未実施。
稼働中の既存版は変更していない。
