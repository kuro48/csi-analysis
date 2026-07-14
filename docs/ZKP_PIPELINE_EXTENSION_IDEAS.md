# ZKPパイプライン拡張のアイディアメモ

作成日: 2026-07-08

現状のZKP回路は解析パイプラインの最終段のみをカバーしている。本メモは、
(1) パイプライン上流（PCA・VMD）を回路に取り込む案、
(2) 入力となる生CSI自体の真正性を保証する案、
の2テーマの検討結果をまとめたもの。

## 現状の整理

| 回路 | 状態 | 証明している命題 |
|------|------|----------------|
| `csi_full_similarity.circom` | 本番フローで使用中（CSIアップロード時） | 秘密のCSIスペクトラム行列から最小コサイン類似度サブキャリアを選び、そのピーク周波数が正常範囲（0.155〜0.505Hz）内 |
| `csi_breathing_normality.circom` | 回路は存在、`/breathing/analyze` には未配線 | 秘密のVMD呼吸成分 `vmd[150]` のDFTピークが6〜22bpm内 |

**課題**: 5-1.ipynbパイプラインのうち、SNRサブキャリア選択→バンドパス→PCA→VMD はPython側で実行しており、回路は「与えられた `vmd` 信号のピーク判定」しか証明しない。証明者が都合のよい `vmd` を捏造できる余地が残る。

---

## テーマ1: PCA・VMDのZKP回路化

### 結論

- **PCA**: 「計算」を「検証」に置き換えれば条件付きで現実的
- **VMD**: Circom/Groth16でのアルゴリズム再現は実質不可能。証明書検証方式かzkVMへの移行が現実解

### 1-1. PCA — witness検証方式（条件付きで現実的）

固有値分解は反復計算（収束依存）で除算・平方根を含むため、回路内で直接計算できない。
代わりに **結果をwitnessとして与え、回路では性質のみ検証する**。

- 第1主成分ベクトル `v` と固有値 `λ` をPython側で計算し秘密witnessとして入力
- 回路内の検証:
  - `C·v ≈ λ·v`（Cは回路内で計算した共分散行列）
  - 射影 `y = X·v` が後段（VMD入力）と一致すること

**制約数の目安**: 共分散計算が支配的で `T × N²`（N=SNR選択後のサブキャリア数）。
N≈30 なら約13.5万制約で、既存の `csi_full_similarity`（971サブキャリア）と同オーダー。

**残る課題**:
- 「λが最大固有値である」ことの厳密な検証は困難。トレースに対する比率の下限チェック等の近似で妥協する
- 固定小数点化によるPython(float)との誤差。既存回路と同様のスケーリング設計が必要

### 1-2. VMD — Circom/Groth16では実質不可能

VMDはADMMによる反復最適化であり、回路化を阻む要素が揃っている:

- 各反復・各周波数ビンで除算（モード更新式、中心周波数のパワー加重平均）
  → 除算1回ごとにwitnessヒント＋レンジチェックが必要
- 収束まで反復（通常数十〜数百回）。固定回数に切っても
  モード数 × ビン数 × 反復数 で制約が数百万〜数千万に爆発
- 固定小数点誤差が反復ごとに蓄積し、Python(float)の結果と回路内結果の一致自体が困難
- 証明生成2秒以内という現行の性能目標と両立しない

### 1-3. 現実的な3つの選択肢

#### 案A: 証明書（certificate）検証方式 ★推奨

VMDのアルゴリズムではなく「VMD出力が満たすべき性質」を検証する。
分解モード `u_k` をwitnessとして与え、回路で以下を検査:

1. **再構成性**: `Σu_k ≈ 入力信号`
2. **狭帯域性**: 呼吸モードのDFTパワーが中心周波数近傍に集中している
3. **正常判定**: そのピークが正常範囲内（既存ロジック）

- 既存のDFTテーブル方式がそのまま流用でき、制約数は現行回路の数倍程度の見込み
- 証明される命題は「厳密にVMDを実行した」から
  「入力は狭帯域モードに分解でき、呼吸モードのピークが正常範囲」に変わるが、
  研究上の主張としてはむしろ本質的

#### 案B: zkVM（RISC Zero / SP1）への移行

パイプライン全体（バンドパス→PCA→VMD→判定）をRust実装し、そのまま証明する。

- 任意計算が証明できるため反復・除算の問題が消える
- 代償: 証明生成時間が分オーダー、Circom/snarkjsスタックの全面変更
- RISC Zeroにはオンチェーン検証器があり、ブロックチェーン記録との統合は可能
- 「パイプライン全体の完全性」を主張したい場合の最有力候補

#### 案C: VMDを回路親和的な処理に置き換え

固定係数のFIRフィルタバンク＋エネルギー最大帯域の選択なら線形演算のみで回路化容易。

- ただし解析手法自体が変わるため、5-1.ipynbとの精度比較が別途必要

---

## テーマ2: 生CSIの真正性保証

パイプラインをどれだけ上流まで回路化しても、**入力の生CSIが実測データである保証**が
なければ「都合のよいCSI行列を捏造できる」問題が残る。以下、案を強度順に列挙。

### 案1: エッジデバイス署名 + 回路内コミットメント検証 ★本命

エッジデバイス（csi-edge-device）が取得直後の生CSI（またはそのハッシュ）に署名する。

- デバイスに秘密鍵を保持させ、キャプチャ単位で
  `sig = Sign(sk_device, Hash(rawCSI) || timestamp || device_id)` を生成
- ZKP回路の公開入力に `Hash(rawCSI)` を含め、回路内で
  「秘密入力のCSIをハッシュすると公開コミットメントに一致する」ことを検証
- 署名自体はオフチェーン/オンチェーンで通常検証（回路内署名検証は重いので分離）
- ハッシュはSNARK親和的な **Poseidon** を採用（SHA-256は回路内で高コスト）

**信頼の根**: デバイスの鍵管理。Raspberry Pi等ならTPM/セキュアエレメント、
最低限ファイルシステム外の鍵格納を検討。

**証明される命題**: 「デバイスXが時刻Tに署名したCSIデータに対し、
所定のパイプラインを適用すると isNormal=1」

### 案2: コミットメントの事前オンチェーン登録（コミット・リビール）

デバイスが測定直後に `Hash(rawCSI)` をブロックチェーン（ZKProofRegistry拡張）へ登録し、
後からその生データに対する解析証明を提出する。

- タイムスタンプの改ざん耐性がブロックチェーン由来で得られる
- 「解析結果を見てから都合のよいデータを作る」後付け攻撃を防げる
- 署名鍵の管理が不要になる代わり、登録トランザクションのコストと遅延が発生
- 案1と組み合わせ可能（署名＋事前コミットで最強）

### 案3: 物理層の整合性チェックを回路内に追加（ソフトな保証）

暗号学的保証ではなく、「本物のCSIらしさ」を回路内で検査する。

- 例: サブキャリア間の振幅相関、時間方向の連続性（急峻なジャンプがない）、
  ノイズフロアの統計的性質などの範囲チェック
- 単体では偽造耐性は弱い（性質を満たすよう捏造可能）が、
  案1/2と併用すれば「署名済みデータが物理的にもっともらしい」ことの追加保証になる
- 制約コストは小さい

### 案4: TEE（Trusted Execution Environment）でのキャプチャ証明

エッジデバイスのTEE（ARM TrustZone等）内でCSIキャプチャ〜ハッシュ計算を行い、
リモートアテステーションで「正規のキャプチャコードが生成したデータ」であることを証明する。

- 保証は強いが、Nexmon CSI等のキャプチャスタックをTEE内に収める実装コストが非常に高い
- 研究プロトタイプの範囲を超えるため、論文では「将来課題」として言及する位置づけが妥当

### 案5: マルチデバイス相互検証

同一環境に複数の受信デバイスを置き、同時刻のCSIの相関が閾値以上であることを
（それぞれの署名付きデータに対して）検証する。

- 単一デバイスの鍵漏洩・捏造への耐性が上がる
- 機材コストと同期の複雑さが増す。マルチパーソン検知研究との親和性はある

### 推奨構成

短期（プロトタイプ）: **案1（Poseidonコミットメント + デバイス署名）**
を最小構成で実装し、回路の公開入力にデータハッシュを追加する。

中期: **案2（事前オンチェーンコミット）** を ZKProofRegistry の拡張として追加し、
測定時刻の改ざん耐性を得る。

これらはテーマ1の回路拡張（案A/B）と独立に進められるが、
公開入力の設計（何をコミットするか: 生CSI / SNR選択後 / PCA射影後）は
回路がどこまで上流をカバーするかに依存するため、セットで決めるのが望ましい。

---

---

## 実装状況（2026-07-14）

テーマ1・案A（証明書検証方式）と、それに伴うパイプライン変更を **別パイプライン**
として実装済み。既存の本番フロー（`csi_full_similarity`）および `/breathing/analyze`
は不変。テーマ2（生CSIの真正性・デバイス署名）は今回のスコープ外（未実装）。

### 実装した命題

証明書回路 `csi_breathing_certificate.circom` は、VMD アルゴリズムそのものではなく
「VMD 出力が満たすべき性質」を検証する:

1. **sel が one-hot**（呼吸モードの指定が正当）— ハード制約
2. **再構成性**: `Σ_k modes[k][t] ≈ vmdInput[t]`
   （誤差エネルギー `Σ(recon-signal)² × 2 ≤ Σ signal²`, 既定50%許容）— ハード制約
3. **selectedMode = Σ_k sel[k]·modes[k]** の DFT で
   - **narrowband**: `peakPower × 20 ≥ totalPower`（ピーク比 ≥ 5%）
   - **正常帯域**: グローバルピークが bin[5, 32]（6〜22bpm）内
4. `isNormal = (正常帯域内) AND (narrowband)`

再構成性をハード制約にしたことで、証明者が「都合のよい単一モード」だけを与える
捏造（旧 `csi_breathing_normality` の弱点）を、入力信号との整合が取れないモードでは
証明が生成できないように塞いだ。回路規模は非線形制約 約7,475（ptau19 で足りる）。

### 追加・変更したファイル

- `zkp/scripts/generate_breathing_certificate_circuit.py` — 回路生成器（新規）
- `zkp/circuits/csi_breathing_certificate.circom` — 生成された回路（新規）
- `zkp/package.json` — `generate/compile/setup:breathing_certificate` スクリプト追加
- `backend/app/services/breathing_pipeline.py` — `prepare_breathing_certificate_input`
  追加、`run_breathing_pipeline_from_matrix` の返り値に `certificate_input` を追加
  （全モード＋入力信号を *共通スケール* で整数化。単一モードを個別正規化する
  `prepare_breathing_zkp_input` とは別処理）
- `backend/app/services/breathing_certificate_service.py` — 証明生成サービス（新規）
- `backend/app/api/endpoints/breathing.py` — `POST /breathing/analyze-certificate` 追加
- `backend/tests/unit/test_breathing_pipeline.py` / `test_breathing_endpoint.py` — テスト追加

### セットアップ・実行

```bash
cd zkp
npm run generate:breathing_certificate   # 回路を再生成（パラメータ変更時）
npm run compile:breathing_certificate    # r1cs / wasm 生成
npm run setup:breathing_certificate      # Trusted Setup（ptau19）→ zkey / vkey
```

エンドポイント: `POST /api/v2/breathing/analyze-certificate`（`.csi` アップロード）
→ 5-1 パイプライン実行 → 証明書 ZKP 証明を生成し `{isNormal, proof, publicSignals,
diagnostics(再構成誤差比・narrowband比), ...}` を返す。

### 残る課題（今後）

- **入力の真正性（テーマ2）は未実装**: `vmdInput` が実測 CSI 由来である保証はない。
  案1（Poseidon コミットメント＋デバイス署名）・案2（オンチェーン事前コミット）は別途。
- **再構成/narrowband 閾値の較正**: 既定は保守的（再構成50%・narrow5%）。
  実データの `diagnostics` を見て回路定数（`RECON_ERR_*` / `NARROW_*`）を締められる。
- **PCA の回路化（案1-1）は未実装**: 証明範囲は VMD 段の証明書検証まで。

---

## 関連ファイル

- `zkp/circuits/csi_full_similarity.circom` — 本番使用中の回路
- `zkp/circuits/csi_breathing_normality.circom` — 5-1パイプライン用回路（未配線・単一モード判定）
- `zkp/circuits/csi_breathing_certificate.circom` — 証明書検証回路（案A・実装済み）
- `zkp/scripts/generate_breathing_certificate_circuit.py` — 証明書回路生成器
- `backend/app/services/zkp_service.py` — 証明生成サービス（full_similarity）
- `backend/app/services/breathing_certificate_service.py` — 証明書証明生成サービス
- `backend/app/services/breathing_pipeline.py` — 5-1パイプライン実装
  （`prepare_breathing_zkp_input` / `prepare_breathing_certificate_input`）
- `backend/app/api/endpoints/breathing.py` — `/analyze` と `/analyze-certificate`
- `docs/BLOCKCHAIN_ZKP_INTEGRATION.md` — ブロックチェーン統合ガイド
