# Phase 2 指示書 — end-to-end 真正性チェーン

親計画: `RESEARCH_ROADMAP.md` / 先行検討: `../ZKP_PIPELINE_EXTENSION_IDEAS.md`（テーマ2）
前提: **Phase 1 完了**（硬化版証明書回路が確定していること）
担当: ZKP・バックエンド・エッジ連携エージェント

## 0. このフェーズのゴール（完了条件）

1. 生CSI（振幅行列）の **Poseidon コミットメント**が証明書回路の公開入力に入り、
   「秘密入力の CSI をハッシュすると公開コミットメントに一致」を回路内で検証できる。
2. パイプラインが **2 回路に分割**され、中間コミットメント `Poseidon(vmdInput)` で連鎖する。
3. エッジデバイスが生CSI に**署名**し、`ZKProofRegistry` にコミットメントを
   **事前登録（コミット・リビール）**できる。署名検証は回路外。
4. Phase 1 の攻撃評価を「設定 B（入力拘束あり）」で再実行し、偽造耐性の向上を定量化。
5. 段別の制約数・証明時間・ガスコスト・エッジ側オーバーヘッドを測定。

新機能は**別エンドポイント・別回路**として追加。本番フロー
（`/csi-data/upload`）と `/breathing/analyze-verifiable` は不変。

## 1. 設計判断（着手前に確定させる）

### 1-1. 何をコミットするか

段間連鎖の設計:

```
rawCSI(振幅行列) --Poseidon--> C0 (公開・オンチェーン事前登録・デバイス署名対象)
   │ 回路①（前処理）
   ├─ サブキャリア選択（選択インデックスを witness、SNR 基準を回路内検証）
   ├─ バンドパス（固定係数 FIR。線形なので回路内で安価）
   ├─ PCA（witness 検証方式: C·v ≈ λv かつ 射影 y = X·v の一致）
   └──Poseidon--> C1 = Poseidon(vmdInput)  （公開・回路①の出力 / 回路②の入力）
   │ 回路②（証明書, Phase 1 硬化版 + C1 一致検証）
   └──> isNormal（公開）
```

- **Poseidon** を使う（SHA-256 は回路内で高コスト）。circomlib の poseidon を利用。
- 大きな行列を 1 回の Poseidon に入れられないため、**Merkle/スポンジ的な逐次ハッシュ**で
  `C0` を構成する設計を先に決める（行ごと Poseidon → ルート等）。
- PCA の witness 検証は制約数が支配的（目安 `T × N²`, N=SNR選択後サブキャリア数 ≈ 30 で約 13.5万）。
  制約超過時は N を削るか、回路①のカバー範囲を「PCA 以降」に縮小して段を切り直す。

### 1-2. 署名方式

- エッジは `sig = Sign(sk_device, C0 || timestamp || device_id)`。
- **回路内で署名検証はしない**（重い）。署名は Registry / バックエンドで通常検証（Ed25519 想定）。
- 回路が保証するのは「C0 にコミットされたデータに所定パイプラインを適用した結果 isNormal」。
  「C0 が実測である」ことは署名 + 事前登録が担保する、という責務分離を文書化。

## 2. 作業手順

### タスク 2-1: コミットメント設計ドキュメント

- `research/phase2_authenticity/COMMITMENT_DESIGN.md`。
- C0（生CSI）と C1（vmdInput）の具体的な Poseidon 構成、フィールド要素への詰め方、
  固定小数点スケール、段の切り方（回路①がどこからどこまでか）を確定。
- 制約数の事前見積もりを表で提示。

### タスク 2-2: 回路②の C1 検証追加（先に軽い方から）

- Phase 1 硬化版 `csi_breathing_certificate` に「`Poseidon(vmdInput) == C1(公開)`」を追加。
- ジェネレータ `zkp/scripts/generate_breathing_certificate_circuit.py` を拡張
  （新パラメータで公開入力 C1 を追加、既存の isNormal 出力は維持）。
- 既存の証明生成サービス `breathing_certificate_service.py` を壊さないよう、
  **新回路名**（例 `csi_breathing_certificate_committed`）で並存させる。

### タスク 2-3: 回路①（前処理）の実装

- 新規回路 `zkp/circuits/csi_preprocess.circom`（ジェネレータも新規）。
- 入力: コミット済み振幅行列（秘密）+ C0（公開）。
- 内容: C0 一致検証 → サブキャリア選択検証 → 固定 FIR バンドパス → PCA witness 検証
  → C1 出力。PCA の固有ベクトル・固有値は Python 側で計算し秘密 witness として渡す。
- Python 側 witness 生成は `breathing_pipeline.py` の
  `select_subcarriers_by_snr` / `bandpass_filter` / PCA 部分の**出力を利用**するが、
  本番関数は編集せず、`research/phase2_authenticity/` 内のラッパで witness を組む。

### タスク 2-4: エッジ署名 + Registry 拡張

- `backend/contracts/ZKProofRegistry.sol` を拡張（または新コントラクト）:
  `registerCommitment(bytes32 c0, uint256 ts, bytes deviceId, bytes sig)` を追加し、
  後から `submitProof(c0, proof, publicSignals)` で証明を提出するコミット・リビール構造。
- エッジデバイス（`csi-edge-device` リポジトリ、別レポ）側の追加は**インターフェース仕様のみ**
  本フェーズで定義（`research/phase2_authenticity/EDGE_INTERFACE.md`）。実装は別タスク/別レポ。
- バックエンドに新エンドポイント（例 `POST /api/v2/breathing/analyze-committed`）を追加。

### タスク 2-5: 評価

- `research/phase2_authenticity/results/`:
  - 段別（回路① / 回路②）制約数・証明生成時間・検証時間
  - Registry のガスコスト（Ganache 実測）
  - エッジ側オーバーヘッド（ハッシュ + 署名 + 登録 POST の時間、見積もりでも可）
  - **Phase 1 攻撃を設定 B で再実行**: C0/C1 が拘束された状態で攻撃①②がどれだけ難化するか。
    「拘束なし成功率 → 拘束あり成功率」の対比表が論文②の核。

## 3. 成果物一覧

```
research/phase2_authenticity/
├── COMMITMENT_DESIGN.md
├── EDGE_INTERFACE.md
├── circuits/                   # csi_preprocess.circom, committed 版証明書回路（ジェネレータ含む）
├── witness/                    # Python witness 生成ラッパ
├── contracts/                  # Registry 拡張案（.sol）
└── results/                    # 制約数・時間・ガス・攻撃再評価
```

## 4. 制約・注意

- 本番フロー・既存回路は不変。新回路・新エンドポイントとして並存させる。
- PCA witness 検証の「λ が最大固有値」の厳密検証は困難。トレース比の下限チェック等の
  近似で妥協し、その限界を文書化（先行メモ 1-1 参照）。
- 回路内 Poseidon の入力サイズに注意。大行列は逐次ハッシュ設計必須。
- 署名鍵管理（TPM/セキュアエレメント）は論文では言及、実装は最小（ファイル鍵）で可。

## 5. 参照

- `docs/ZKP_PIPELINE_EXTENSION_IDEAS.md` テーマ2（案1 署名+コミット, 案2 事前オンチェーン）
- `backend/app/services/breathing_pipeline.py`
  - `select_subcarriers_by_snr` (L213), `bandpass_filter` (L194),
    `select_respiration_pc` (L283), `prepare_breathing_certificate_input` (L452)
- `zkp/scripts/generate_breathing_certificate_circuit.py`
- `backend/contracts/ZKProofRegistry.sol`, `backend/app/services/blockchain_service.py`
- エッジ: https://github.com/kuro48/csi-edge-device.git
