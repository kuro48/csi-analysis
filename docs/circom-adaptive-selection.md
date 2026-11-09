# Circom内でのサブキャリア選択（実験版）

## 今回の変更

CSIの評価・比較・選択をCircom内に実装した。Pythonで候補を選ぶ処理は追加していない。
全候補のI/Qを秘密入力にし、回路自身が1本を選択して、その波形だけをLomb–Scargleで処理する。
既存の等間隔8本版は残し、新版は別回路として追加した。

[検証記録・再検証用の証明ファイル](progress/2026-11-09-circom-adaptive/README.md)も保存した。
18テストと合成CSIでのGroth16証明生成・検証に成功し、5種類の公開値改ざんを拒否した。
証明生成20.999秒、検証0.010秒は同一プロセス内での1回の計測で、鍵生成の時間は別に記録している。

| 項目 | 従来のe2e回路 | 新しいadaptive回路 |
|---|---|---|
| 回路ファイル | `csi_lomb_scargle_end_to_end.circom` | `csi_lomb_scargle_adaptive.circom` |
| 64時刻の入力候補数 | 外部で選んだ8本 | 最大64本、全候補を渡す |
| サブキャリアの選択 | 8本の正常帯域LSピークを比較 | 全候補の変動・滑らかさを回路内で比較 |
| LSの実行本数 | 8 | 選択した1本 |
| コミット対象 | 入力された8本 | 入力された全候補とパディング |
| 公開信号数 | 69 | 70 |
| R1CS制約数（O1） | 807,453 | 625,867 |
| 稼働中システムへの接続 | 既存版 | 未接続、独立した実験版 |

制約数は約22.49%減った。ただし選択基準とLS実行本数も変えているため、
同じ判定アルゴリズムの単純な高速化比較ではない。精度の改善を示す値でもない。

## 回路が行う計算

各候補について、オフセットを除いた整数I/Qから次を計算する。Nは64。

```text
p[t] = I[t]^2 + Q[t]^2
S = sum(p[t])
V = N * sum(p[t]^2) - S^2
D = sum((p[t] - p[t-1])^2), t = 1..N-1
score = V^2 / ((S^2 + 1) * (V + N*D + 1))
```

受信電力そのものが大きいだけの候補より、相対的な振幅変動があり、隣接点間で激しく跳ばない候補を優先する。
候補にする条件は `S >= N*16`、`V > 0`、`V <= S^2`。
最後の条件は電力の変動係数の二乗が1以下という条件で、疎な大スパイクなどを除くための固定ヒューリスティック。
実データに対する最適化・妥当性確認はまだ行っていない。

Circom内では除算せず、分子と分母を交差乗算して順位を比較する。同点は小さい列番号を優先する。
有効候補がゼロなら制約違反となり、呼吸結果を生成しない。
`selectedSubcarrier` やscoreは入力として受け取らない。

主要な制約は以下。実装全体は `zkp/circuits/csi_motion_selector.circom` を参照。

```circom
numerator[sc] <== variation[sc] * variation[sc];
denominator[sc] <== (totalSquared[sc] + 1)
    * (variation[sc] + N * roughness[sc] + 1);
left[sc] <== eligibleNumerator[sc] * bestDenominator[sc];
right[sc] <== bestNumerator[sc] * denominator[sc];
better[sc] = GreaterThan(240);
better[sc].in[0] <== left[sc];
better[sc].in[1] <== right[sc];
bestIndex[sc + 1] <== bestIndex[sc]
    + better[sc].out * (sc - bestIndex[sc]);
```

12bitのI/Qと64時刻以下という上限から、比較の積は `2^234` 未満。
240bit比較を使い、BN254の体の剰余によって大小関係が逆転しない範囲に抑えている。
積を中間signalに分割することで二次制約にしている。
Circomの制約形式については[公式ドキュメント](https://docs.circom.io/circom-language/constraint-generation/)を参照。

## コミットメントと公開出力

I/Qは符号付き値に2048を加えた0..4095。回路内で全要素を12bitに制約する。
実際の候補数 `candidateCount` より後の列はI/Qとも2048に制約する。

全候補を時刻→列の順に並べ、`I + 4096*Q` の24bit表現を10ペアずつ240bitに詰める。
Poseidon(5)のヘッダーは `[2026110901, N, capacity, candidateCount, nonce]`。
以後Poseidon(16)に `[直前のハッシュ, 15個のpacked値]` を入れ、最終ブロックの不足分は0で埋める。
選ばれなかった候補を変えてもコミットメントが変わる。nonceは秘密かつ非ゼロ。

公開信号の順序は以下。選択波形やスコアは公開しない。

```text
0      csiCommitment
1      isNormal
2      selectedSubcarrier（入力プール中の列番号）
3      estimatedFrequencyBin（正常帯域内ピーク）
4      globalPeakFrequencyBin（全探索帯域内ピーク）
5..68  timestampsMs[0..63]
69     candidateCount
```

isNormalの条件とLS周波数グリッドは既存のものを再利用する。
正常帯域への適合度で候補を選んでいないため、帯域外の候補が選ばれた場合もそのまま判定する。
このコミットメントは「与えられたプールに対して正しく選択した」ことを結び付ける。
収集装置がプールを欠落なく提出したこと、患者本人の測定であること、計測時刻の真正性までは保証しない。

## 再現手順

リポジトリルートで実行する。Circomと `zkp/node_modules` が必要。

```sh
# 選択・入力整形・LS接続・旧回路の回帰テスト
node zkp/scripts/test_adaptive_lomb.cjs

# 64候補版をコンパイル
mkdir -p .local/circom-adaptive/build
circom zkp/circuits/csi_lomb_scargle_adaptive.circom \
  --O1 --r1cs --wasm --sym -l zkp/node_modules \
  -o .local/circom-adaptive/build

# 2^20用の公開Phase 1資料を取得（約1.21GB）
curl --fail --location \
  https://circom.info/powersOfTau28_hez_final_20.ptau \
  --output .local/circom-adaptive/powersOfTau28_hez_final_20.ptau
```

取得後は[snarkjs公式の表](https://github.com/iden3/snarkjs/blob/master/README.md)の
BLAKE2b-512ハッシュと照合する。今回照合した値:

```text
89a66eb5590a1c94e3f1ee0e72acf49b1669e050bb5f93c73b066b564dca4e0c7556a52b323178269d64af325d8fdddb33da3a27c34409b821de82aa2bf1a27b
```

```sh
node zkp/scripts/prove_adaptive_lomb.cjs \
  --build .local/circom-adaptive/build \
  --ptau .local/circom-adaptive/powersOfTau28_hez_final_20.ptau
```

このコマンドは合成CSIでwitness作成・R1CS検査・実験用鍵生成・ランダムな追加contribution・
Groth16証明生成・検証・公開出力改ざんの拒否を確認し、専用の `proof-run-*` ディレクトリに
コード実行結果 `report.json` と鍵・証明を保存する。既存の配備済み鍵には書き込まない。
実験用の単独contributionであり、公開運用向けの複数参加者による鍵生成は別途必要。
入力とwitnessは秘密データなのでGit管理外の `.local` に保存する。

## 実測入力とユーザー側の作業

回路実装・合成データでの試験にユーザー側の操作は不要。
実測評価では、64時刻に整形済みの **全候補** のI/Qと相対ミリ秒時刻をJSONにする。
`--input /path/to/encoded-csi.json` を上のコマンドに加えると実測入力を利用できる。

```json
{
  "csiI": [["説明用: 実際は0..4095の整数を候補数分、64行"]],
  "csiQ": [["説明用: csiIと同じ形状"]],
  "timestampsMs": ["説明用: 0から始まる単調増加の整数64個"]
}
```

これは形式の説明であり、そのまま投入できるデータではない。
I/Qの共通スケールでの量子化、64時刻への整形は回路外の入力処理として必要。
`adaptive_lomb_input.cjs` はJSONの形状・範囲を検査し、候補の順序を保ってゼロパディングし、nonceを作る。
評価や候補削減は行わない。従来の `prepare_input.py` は8本を間引くため、新版への入力作成には使わない。

初期のデモランナーは64候補専用だった。手元のPicoScenes実測には4,004列のデータがあり、
この入力を64候補版へ渡すと明示的にエラーにする。黙って64本へ間引くことはしない。
テンプレート `LombScargleCSIAdaptive(CANDIDATES)` は最大4,096候補まで指定できるが、
後続作業で4,004列用main、入力整形、ネイティブ証明器、WebUI/APIと両台帳への接続を追加した。
実行結果と手順は[4,004列版の進捗報告](progress/2026-11-09-adaptive-4004/README.md)を参照。
その後、[Python参照との選択比較](progress/2026-11-09-selection-comparison/README.md)を追加した。
実測5件・合成12件で同式の整数計算との一致を確認した一方、間引きによる選択変化と、
呼吸より雑音を選ぶ合成例を確認した。正解ラベルとの実測精度評価は引き続き未実施。
PicoScenesの列にはアンテナ対も含まれるため、列番号と物理サブキャリアの対応も取り込み時に保持する必要がある。

## 適用範囲と残作業

- 振幅変動に対するヒューリスティック。合成評価で雑音・低周波変動を優先する弱点があり、実環境で呼吸・体動・環境ノイズを区別する性能は未確定。
- 位相だけが変わり電力が一定の信号は対象外。隣接変動Dには時間間隔補正を入れていない。
- 固定された低電力・変動係数閾値は、量子化と実測環境によって有効性が変わる。
- 旧回路を共通テンプレートへ分離したが、旧mainのパラメータと動作は維持。
- 新版は公開信号数・コミット方式・選択規則が変わる。旧鍵・旧Verifierとは互換性がない。
- WebUI/API・Fabric・EVMに `adaptive4004` プロファイルを追加した。旧方式は `legacy` として保持。
  Sepoliaの実デプロイには[テストETHの準備](adaptive-sepolia-setup.md)が必要。
  エッジ配布物へのネイティブ証明器の同梱は別作業。収集端末は全CSIをサーバーへ送り、サーバーで証明できる。
- 本番向けには、実測CSIでの既存方式との比較、対象プールの仕様確定、回路レビュー、鍵生成、チェーンへの登録が残る。
