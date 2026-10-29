# Phase 2: Python／Circom ハイブリッド実験

- 実装内容とスクリーンショット用コード: [`変更記録.md`](変更記録.md)
- 処理別コミットメントと遷移証明の議論: [`設計議論記録.md`](設計議論記録.md)
- Poseidonの正規化仕様: [`COMMITMENT_DESIGN.md`](COMMITMENT_DESIGN.md)
- 英語版の詳細ログ: [`IMPLEMENTATION_LOG.md`](IMPLEMENTATION_LOG.md)
- 入力例: [`example_manifest.csv`](example_manifest.csv)

## 実データ比較

```bash
cd backend
python3 scripts/run_hybrid_benchmark.py \
  ../zkp/experiments/phase2_authenticity/example_manifest.csv --repeat 3

cd ..
python3 zkp/experiments/phase2_authenticity/generate_report.py
```

結果は`results/runs.jsonl`、`results/method_runs.csv`へ追記され、集計後に
`results/REPORT.md`と`results/comparison.svg`が生成される。実データと生成結果は
Git管理対象外である。
