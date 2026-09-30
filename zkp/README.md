# ZKP (Zero-Knowledge Proof) System

Wi-Fi CSI 呼吸監視システムの Circom / snarkjs (Groth16) 実装。

CSIアップロード時は 5-1 系（VMD）と Lomb--Scargle の2経路を同じCSIで解析し、
それぞれの回路で「呼吸数が正常帯域にあるか」を秘密入力のまま証明する。

## 構成

```
zkp/
├── circuits/
│   ├── csi_breathing_certificate.circom     # VMD出力の性質を検証する証明書回路
│   ├── csi_lomb_scargle_normality.circom    # Lomb--Scargle正常判定回路
│   ├── lomb_scargle_timestamp_basis.circom  # 上記のsin/cos基底
│   └── csi_breathing_normality.circom       # 旧・呼吸正常判定回路（未使用）
├── scripts/
│   ├── generate_breathing_certificate_circuit.py
│   ├── generate_lomb_scargle_circuit.py
│   ├── generate_breathing_circuit.py
│   ├── fetch_ptau24.sh                      # 2^24 Powers of Tau の取得
│   └── measure_stage_profile.py             # 工程別の制約数・時間の計測
├── test/                                    # mocha による回路テスト
├── build/                                   # コンパイル出力（r1cs / wasm / sym）
└── keys/                                    # zkey・検証鍵・Powers of Tau
```

`build/` と `keys/` は生成物のため Git 管理外。

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

## テスト

```bash
npm test
```

## バックエンドからの利用

`ZKP_AUTO_COMPILE=true` で起動すると、`backend/entrypoint.sh` が
回路のコンパイルと Trusted Setup を自動で行う。証明の生成・検証は
`backend/app/services/zkp_circuit_service.py` とその派生サービスが担当する。
