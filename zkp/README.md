# ZKP (Zero-Knowledge Proof) System

Wi-Fi CSI 呼吸監視システムの Circom / snarkjs (Groth16) 実装。

CSIアップロード時は 5-1 系（VMD）と Lomb--Scargle の2経路を同じCSIで解析し、
それぞれの回路で「呼吸数が正常帯域にあるか」を秘密入力のまま証明する。

## 構成

```
zkp/
├── circuits/
│   ├── csi_breathing_certificate.circom     # VMD出力の性質を検証する証明書回路
│   ├── csi_breathing_certificate_committed.circom # VMD入力を公開C1へ拘束
│   ├── csi_preprocess_projection.circom     # 縮約固定小数点PCA射影の検証
│   ├── csi_lomb_scargle_normality.circom    # Lomb--Scargle正常判定回路
│   ├── lomb_scargle_timestamp_basis.circom  # 上記のsin/cos基底
│   └── csi_breathing_normality.circom       # 旧・呼吸正常判定回路（未使用）
│   └── csi_vmd_approx.circom                # 固定反復の近似VMD回路
├── scripts/
│   ├── generate_breathing_certificate_circuit.py
│   ├── generate_lomb_scargle_circuit.py
│   ├── generate_breathing_circuit.py
│   ├── fetch_ptau24.sh                      # 2^24 Powers of Tau の取得
│   └── measure_stage_profile.py             # 工程別の制約数・時間の計測
│   ├── generate_vmd_approx_circuit.py       # 近似VMD回路生成
│   └── setup_vmd_approx.js                  # 専用zkeyのTrusted Setup
├── test/                                    # mocha による回路テスト
├── build/                                   # コンパイル出力（r1cs / wasm / sym）
└── keys/                                    # zkey・検証鍵・Powers of Tau
```

`build/` と `keys/` は生成物のため Git 管理外。

## 証明付き中間ハッシュ

実運用で並列実行する VMD 近似回路と Lomb--Scargle 回路は、秘密入力、
公開入力、計算結果を Poseidon (BN254) のチェーンへ取り込み、
`intermediateHash` を公開出力として返す。ハッシュは Groth16 の制約内で
計算されるため、証明検証に成功したハッシュだけを工程の監査識別子として使える。
辞書攻撃を避けるため nonce は128-bitの秘密入力とし、レスポンスには含めない。

`/analyze-verifiable` は最初に `csi_preprocess_projection.circom` を検証し、その
`projectionCommitment` を VMD / Lomb--Scargle 両回路の公開 `parentCommitment` として渡す。
後段の `intermediateHash` も親コミットメントを取り込むため、別の前処理証明への
差し替えは検出される。APIの `proofChain.edges[].verified` は公開信号の一致も検査する。

ただし、前処理回路は32点の縮約射影、後段は128点または3×384点を使うため、現段階の
連携が保証するのは証明間のコミットメント連続性である。縮約射影から後段入力への変換
そのものを保証するには、共通の完全PCA出力を扱う遷移回路が必要となる。

## セットアップ

```bash
npm install
```

### VMD証明書回路

```bash
npm run generate:breathing_certificate
npm run compile:breathing_certificate
npm run setup:breathing_certificate   # 2^19 ptau
```

### コミットメント付き証明書・前処理射影

既存の証明書回路と並存し、Python推定結果のC1拘束と段階的な前処理検証に使う。

```bash
npm run generate:breathing_certificate_committed
npm run compile:breathing_certificate_committed
npm run setup:breathing_certificate_committed
npm run compile:preprocess_projection
npm run setup:preprocess_projection
```

コミットメントの正規化仕様と実験方法は
`zkp/experiments/phase2_authenticity/COMMITMENT_DESIGN.md` を参照。

### Lomb--Scargle回路

約750万制約（非線形約626万）あり、2^24 の phase-2 Powers of Tau（約19GB）が必要。

```bash
npm run ptau:fetch24        # 中断しても再実行でレジュームする
npm run generate:lomb_scargle
npm run compile:lomb_scargle
npm run setup:lomb_scargle
```

Trusted Setup と証明生成は Node のヒープを広げて実行する
（`ZKP_NODE_MAX_OLD_SPACE_MB` で変更可能）。詳細は
`docs/LOMB_SCARGLE_COMPARISON.md` を参照。

### Circom近似VMD回路

詳細な数式、入力縮約、公開出力、Python VMDとの違いは `docs/VMD_APPROXIMATION.md` を参照してください。

```bash
npm run generate:vmd_approx
npm run compile:vmd_approx
npm run setup:vmd_approx
```

## テスト

```bash
npm test
```

## バックエンドからの利用

`ZKP_AUTO_COMPILE=true` で起動すると、`backend/entrypoint.sh` が
回路のコンパイルと Trusted Setup を自動で行う。証明の生成・検証は
`backend/app/services/zkp_circuit_service.py` とその派生サービスが担当する。

## 実験・証明成果物の保存先

ZKP関連はこの `zkp/` 配下に集約する。実験は `experiments/`、共通回路は `circuits/`、共通実行コードは `scripts/` に保存し、リポジトリ直下の `research/` へ分散させない。

- 最新比較結果: [experiments/2026-10-26/remeasure_public/report.html](experiments/2026-10-26/remeasure_public/report.html)
- 各証明の公開中間値: [波形ビューア](experiments/2026-10-26/remeasure_public/index.html)
- 過去の証明・測定JSONに記録された旧パスは生成時点の履歴として保持する。証明・回路・公開値のバイト列は移動で変更しない。
