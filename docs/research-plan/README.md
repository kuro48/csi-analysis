# 研究計画ドキュメント一覧

Wi-Fi CSI 非接触呼吸監視システムの「検証可能性 × バイタルセンシング」研究計画。
zkVM 路線は凍結し、**Python + Circom を主軸**に 3 フェーズで新規性を追う。

## 読む順序

1. **`RESEARCH_ROADMAP.md`** — 全体戦略・フェーズ関係・スケジュール・スコープ外事項。まずこれ。
2. 各フェーズ指示書（他エージェントへの作業依頼はこれ単体で自己完結するよう記述）:
   - **`PHASE1_BRIEF.md`** — 証明書方式の健全性ギャップの形式化・攻撃・較正（最優先・独立着手可）
   - **`PHASE2_BRIEF.md`** — end-to-end 真正性チェーン（Phase 1 完了が前提）
   - **`PHASE3_BRIEF.md`** — folding 連続監視（Phase 1 完了が前提・Go/No-Go 判断が先）

## フェーズ依存関係

```
Phase 1（回路硬化）── 前提 ──> Phase 2（真正性チェーン）
        └─────────── 前提 ──> Phase 3（folding, 並行可 / まず feasibility）
```

## エージェントへの共通ルール

- 本番コード（`backend/app/`, `zkp/scripts/`, `zkp/circuits/`, `backend/contracts/`）は
  各 BRIEF が明示的に許可した範囲以外**編集しない**。研究成果物は `research/<phase>/` に置く。
- 本番フロー（`csi_full_similarity` / `/csi-data/upload` / `/breathing/analyze`）は不変。
  新機能は別回路・別エンドポイントとして並存させる。
- zkVM（`zkvm/`）は削除も追加開発もしない。凍結。
- 実データ（`.csi`）が無い場合は合成データで進め、その旨を成果物に明記する。

## 最初の一手

`PHASE1_BRIEF.md` タスク 1-1（制約チェッカ）と 1-3 攻撃①（選択モードエネルギー下限の
欠如を突く最小構成）。結果が Phase 2/3 の回路設計を直接決める。
