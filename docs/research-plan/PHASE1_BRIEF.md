# Phase 1 指示書 — 証明書方式の健全性ギャップの形式化と攻撃評価

親計画: `RESEARCH_ROADMAP.md` / 先行検討: `../ZKP_PIPELINE_EXTENSION_IDEAS.md`
担当: 解析・ZKP エージェント（Python + Circom）

## 0. このフェーズのゴール（完了条件）

1. 証明書回路 `csi_breathing_certificate.circom` の制約を Python で忠実に再実装した
   **制約チェッカ**が存在し、既存の正規入力（`prepare_breathing_certificate_input` の出力）を
   回路と bit 単位で同一判定できる（回路の実証明と 1 件以上で突き合わせ済み）。
2. **少なくとも 1 つの偽造攻撃例**: 呼吸として異常な信号から `isNormal=1` を満たす
   `(vmdInput, modes, sel)` を構成できることを、チェッカ（可能なら実回路）で実証。
3. 閾値掃引による「正規データ証明成功率 vs 偽造成功率」トレードオフ曲線（図・CSV）。
4. 対策制約を加えた**硬化版回路のジェネレータ改修案**（差分パッチ or 具体的設計）。

コードは新規ディレクトリ `research/phase1_soundness/` 配下に置き、
本番フロー（`breathing_pipeline.py` の既存関数・`generate_breathing_certificate_circuit.py`）は
**このフェーズでは編集しない**（硬化は成果物として提案するに留め、適用は別タスク）。

## 1. 前提知識：現行回路が検証している命題

`zkp/circuits/csi_breathing_certificate.circom`（ジェネレータ:
`zkp/scripts/generate_breathing_certificate_circuit.py`）のパラメータと制約:

- 秘密入力: `vmdInput[T]`, `modes[K][T]`, `sel[K]`（T=150, K=5）
- 公開出力: `isNormal`
- 制約:
  1. `sel` が one-hot（各 0/1、総和 1）— ハード
  2. 再構成性: `Σ_t (Σ_k modes[k][t] − vmdInput[t])² × RECON_ERR_DEN
     ≤ Σ_t vmdInput[t]² × RECON_ERR_NUM`（既定 `1/2` = 誤差エネルギー ≤ 50%）— ハード
  3. `selectedMode = Σ_k sel[k]·modes[k]` の DFT（整数 COS/SIN テーブル, NUM_FREQ=101）で
     - narrowband: `peakPower × NARROW_DEN ≥ totalPower × NARROW_NUM`（既定 `1/20` = 5%）
     - 正常帯域: `argmax(power) ∈ [NORMAL_LOW_BIN=5, NORMAL_HIGH_BIN=32]`（≈6–22bpm）
  4. `isNormal = 正常帯域内 AND narrowband`

定数の所在（ジェネレータ冒頭）:
`T=150, K=5, NUM_FREQ=101, NORMAL_LOW_BIN=5, NORMAL_HIGH_BIN=32, COS_SCALE=1000,
MODE_MAX_ABS=1000, RECON_ERR_NUM=1, RECON_ERR_DEN=2, NARROW_NUM=1, NARROW_DEN=20`。
DFT テーブルは `COS_TABLE[f][t] = round(cos(2π·(0.05 + f·0.01)·t / 5.0)·1000)`（SIN も同様、Fs=5.0Hz）。

**着目すべき構造的穴（最優先で検証する仮説）**:
選択モードの**エネルギー下限制約が存在しない**。再構成性は「全モードの和」に対する制約で、
「選択された 1 モードが入力のどれだけを説明するか」は問われない。
したがって「異常成分を非選択モードに全部押し込み、正常帯域の微小な単一周波数モードを 1 本
選択モードにする」構成が、再構成性・narrowband・正常帯域を同時に満たしうる。
これが成立すれば攻撃例①として最も明快。

## 2. 作業手順

### タスク 1-1: 制約チェッカの実装

- `research/phase1_soundness/certificate_checker.py` を新規作成。
- 関数 `check_certificate(vmdInput: list[int], modes: list[list[int]], sel: list[int]) -> dict`
  を実装。回路と**同じ整数演算・同じ COS/SIN 整数テーブル**を使い、
  各制約の成否と `isNormal`、および中間量（errEnergy, sigEnergy, peakPower, totalPower,
  argmax bin, 選択モードエネルギー）を返す。
- COS/SIN テーブルは `generate_breathing_certificate_circuit.py` の `build_table` と
  同一式で生成（浮動小数ではなく round 後整数で保持）。
- **検証**: `prepare_breathing_certificate_input`（`breathing_pipeline.py:452`）が返す
  正規入力を 1 サンプル以上通し、`diagnostics` の recon_ok / narrow_ok と一致することを確認。
  可能なら実回路（`npm run compile/setup:breathing_certificate` 済みなら witness 生成）で
  `isNormal` を突き合わせ、bit 単位一致をログに残す。

### タスク 1-2: 攻撃者モデルの定義（ドキュメント）

- `research/phase1_soundness/THREAT_MODEL.md` を作成。以下を明記:
  - 敵の能力: 回路定数を完全に知る証明者。`(vmdInput, modes, sel)` を自由に選べる
    （＝入力真正性なしの現状）。目標は `isNormal=1` の witness を作ること。
  - 2 つの設定を区別:
    - **設定 A（拘束なし）**: vmdInput も自由。Phase 1 の主対象。
    - **設定 B（拘束あり）**: vmdInput が実測データ由来にコミット済み（Phase 2 後の世界）。
      Phase 1 では「設定 B なら攻撃がどう難化するか」を定性的に述べるに留め、
      定量評価は Phase 2 に引き継ぐ。
  - 「呼吸として異常」の定義: 例）真の呼吸数が正常帯域外（<6 or >22bpm）、
    または無呼吸（呼吸帯域にピークなし）。合成データで定義。

### タスク 1-3: 攻撃探索の実装

- `research/phase1_soundness/attack_search.py`。
- **攻撃①（構造的穴の直接利用）**: 異常な目標信号 `s`（例: 頻呼吸 30bpm や無呼吸ノイズ）
  を与え、`modes[0]` に正常帯域の単一正弦（例 12bpm）を微小振幅で置き、
  `modes[1]` に `s − modes[0]` を入れ、残りを 0、`sel=e_0` とする。
  vmdInput は再構成性を満たすよう `Σ modes` に一致 or 近接させる。
  チェッカで `isNormal=1` を狙う。まずこの最小構成が通るかを確認。
- **攻撃②（最適化ベース）**: 攻撃①が閾値で弾かれる場合、`modes` を変数として
  射影勾配 / SLSQP 等で「制約を満たしつつ vmdInput を目標異常信号に近づける」最適化。
  float で解き整数化 → チェッカで最終判定。
- 各成功例について「目標信号の真の呼吸数」「再構成誤差比」「narrow比」「選択モードが
  入力エネルギーに占める割合」を記録。

### タスク 1-4: 閾値較正実験

- `research/phase1_soundness/calibration.py`。
- 正規データセット（実 `.csi` があれば `run_breathing_pipeline_from_matrix` 経由、
  無ければ合成正常呼吸 8–18bpm）と異常/攻撃データに対し、以下を掃引:
  - `RECON_ERR`（例 0.2〜0.6）
  - `NARROW`（例 0.02〜0.2）
  - **新設**: 選択モードエネルギー下限比 `SEL_ENERGY`（選択モードエネルギー / 入力エネルギー ≥ 閾値）
- 各設定で「正規データ証明成功率」と「攻撃成功率」を集計し、
  トレードオフ曲線（CSV + matplotlib PNG）を `research/phase1_soundness/results/` に出力。

### タスク 1-5: 硬化版回路の設計提案

- `research/phase1_soundness/HARDENING.md`。
- タスク 1-4 で有効だった対策（本命は選択モードエネルギー下限制約）について、
  `generate_breathing_certificate_circuit.py` への具体的な追加制約を Circom 疑似コードで示す。
  例: `selEnergy × SEL_DEN ≥ sigEnergy × SEL_NUM` をハード制約に追加。
- bit 幅への影響（`selEnergy` の上限見積もり）と ptau サイズ影響を記載。
- **実際のジェネレータ改修は行わない**（別タスクで適用）。推奨定数値のみ提示。

## 3. 成果物一覧

```
research/phase1_soundness/
├── certificate_checker.py      # 回路制約の Python 忠実再実装
├── attack_search.py            # 攻撃①②
├── calibration.py              # 閾値掃引
├── THREAT_MODEL.md             # 攻撃者モデル
├── HARDENING.md                # 硬化版回路の設計提案（適用は別タスク）
└── results/                    # トレードオフ曲線 CSV / PNG, 攻撃例 JSON
```

## 4. 制約・注意

- 本番コード（`backend/app/`, `zkp/scripts/`, `zkp/circuits/`）は**編集しない**。
  参照のみ。硬化は提案ドキュメントとして残す。
- 整数演算は回路と完全一致させる（Python の float FFT ではなく整数 COS/SIN テーブル DFT）。
  ここがズレると攻撃の成否判定が信用できない。
- 実 `.csi` データが無い場合は合成データで進め、その旨を各成果物に明記。
- 攻撃が「できない」結果でも失敗ではない。閾値の妥当性の証拠として較正論文に使う
  （ただしエネルギー下限欠如は構造的なので攻撃①が通る可能性は高い）。

## 5. 参照

- `backend/app/services/breathing_pipeline.py`
  - `prepare_breathing_certificate_input` (L452) — 正規入力生成、diagnostics 定義
  - `estimate_breathing_rate_by_vmd_global_peak` (L306) — VMD 実行と選択モード
  - 定数 `ZKP_CERT_*`（L79–83）, `ZKP_T=150`, `ZKP_TARGET_FS=5.0`
- `zkp/scripts/generate_breathing_certificate_circuit.py` — 回路定数・テーブル生成式
- `zkp/circuits/csi_breathing_certificate.circom` — 生成済み回路（読むだけ）
- `backend/app/services/breathing_certificate_service.py` — 証明生成の実フロー
