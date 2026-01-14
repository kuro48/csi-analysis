# ZKP Scripts - サブキャリア類似度計算

ZKPシステムで各サブキャリアごとのコサイン類似度を計算し、上位5つの低類似度サブキャリアを出力するスクリプト群です。

## 推奨ワークフロー: ZKP回路 vs Python高精度計算

```bash
# 1. ZKP回路で証明を生成（回路内での計算結果を取得）
npm run prove:all_subcarriers

# 2. Python高精度計算でZKP結果と比較
npm run compare:accuracy
```

このワークフローでは、ZKP回路内での近似計算とPythonの高精度計算を比較し、ZKP近似の精度を検証できます。

## スクリプト一覧

### 1. prove_from_all_subcarriers.js
**ZKP回路で証明を生成し、回路内での類似度計算結果を表示**

- ZKP回路を使用して証明を生成
- 回路内で全サブキャリアの類似度を計算（近似計算）
- 上位5つの低類似度サブキャリアを表示
- 証明の検証
- 入力データと結果を保存（Python比較用）

```bash
cd zkp
npm run prove:all_subcarriers
```

**出力例:**
```
📉 Top 5 Lowest Similarities (ZKP Circuit):
  1. Subcarrier 123: 0.654321
  2. Subcarrier 234: 0.678901
  3. Subcarrier 45: 0.689012
  4. Subcarrier 178: 0.701234
  5. Subcarrier 89: 0.712345

✅ PROOF VERIFIED SUCCESSFULLY!
```

### 2. calculate_all_subcarrier_similarity.js
**JavaScript直接計算で全サブキャリアの類似度を高速計算**

開発モード専用 - ZKPを使わずに類似度を直接計算（デバッグ・検証用）

- 高速な類似度計算（ZKP不要）
- 詳細な統計情報
- 上位5つの低類似度と高類似度サブキャリア
- 結果をJSONファイルに保存

**注意**: このスクリプトは独立して動作し、ZKPやPythonとの比較は行いません。
主にデバッグや個別検証用途で使用します。

```bash
cd zkp
npm run calc:similarities

# カスタムデータファイルを使用する場合
node scripts/calculate_all_subcarrier_similarity.js path/to/data.json
```

**出力例:**
```
📈 Statistics:
  Mean:     0.987654
  Median:   0.991234
  Std Dev:  0.012345
  Min:      0.654321
  Max:      0.999876

📉 Top 5 Lowest Similarities:
  1. Subcarrier 123: 0.654321 (dot=123456.78, norm_ref=5678.90, norm_cand=5690.12)
  2. Subcarrier 234: 0.678901 (dot=134567.89, norm_ref=5678.90, norm_cand=5701.23)
  ...
```

### 3. compare_similarity_accuracy.py
**Python高精度リファレンス実装でZKP回路の精度検証**

開発モード専用 - NumPyを使用した高精度計算とZKP回路結果の比較

- NumPyによる高精度コサイン類似度計算（リファレンス実装）
- ZKP回路結果との精度比較（近似計算の精度検証）
- 詳細な統計分析（平均、中央値、標準偏差、四分位数）
- 結果をJSONファイルに保存

**使い方**:
1. 先に `npm run prove:all_subcarriers` でZKP証明を生成
2. その後、このスクリプトを実行して比較

```bash
cd zkp
npm run compare:accuracy

# または直接Pythonで実行
python3 scripts/compare_similarity_accuracy.py

# カスタムデータファイルを使用する場合
python3 scripts/compare_similarity_accuracy.py path/to/data.json
```

**出力例:**
```
📂 Loading input data from latest ZKP results: similarities_2024-01-14T12-00-00-000Z.json

📈 Statistics (Python High-Precision):
  Mean:     0.98765432
  Median:   0.99123456
  Std Dev:  0.01234567
  Min:      0.65432109
  Max:      0.99987654
  Q25:      0.97654321
  Q75:      0.99234567

📉 Top 5 Lowest Similarities:
  1. Subcarrier 123: 0.65432109 (dot=123456.78, norm_ref=5678.90, norm_cand=5690.12)
  ...

🔍 Accuracy Comparison (Python High-Precision vs ZKP Circuit):
  Mean Absolute Difference:   0.00001234
  Max Absolute Difference:    0.00005678
  Median Absolute Difference: 0.00000987
  Std Dev of Differences:     0.00001543

📊 Top 5 Lowest Similarities Comparison:
  Rank | Python SC | Python Sim | ZKP SC    | ZKP Sim    | Diff
  -----|-----------|------------|-----------|------------|----------
  1    |       123 | 0.654321   |       123 | 0.654310   | 0.00001100
  2    |       234 | 0.678901   |       234 | 0.678895   | 0.00000600
  ...

🔐 ZKP Proof Status: ✅ Valid
  Min Similarity (ZKP): 0.654310
  Min Index (ZKP):      123
```

## 環境別の使い分け

### 本番環境
- **使用可能**: `prove_from_all_subcarriers.js`（ZKP証明のみ）
- **使用不可**: `calculate_all_subcarrier_similarity.js`, `compare_similarity_accuracy.py`（開発専用）

環境変数設定（本番）:
```bash
ZKP_ENABLED=true
ZKP_DEVELOPMENT_MODE=false
ALLOW_JS_SIMILARITY=false
ALLOW_PYTHON_SIMILARITY=false
```

### 開発環境
- **全て使用可能**
- **推奨ワークフロー**: ZKP証明生成 → Python精度比較

環境変数設定（開発）:
```bash
ZKP_ENABLED=true
ZKP_DEVELOPMENT_MODE=true
ALLOW_JS_SIMILARITY=true  # JavaScript直接計算を許可（デバッグ用）
ALLOW_PYTHON_SIMILARITY=true  # Python高精度計算を許可（精度検証用）
```

## ZKP vs Python 比較の意義

### ZKP回路（prove_from_all_subcarriers.js）
- **目的**: プライバシー保護された証明可能な計算
- **計算方式**: 固定小数点演算 + Newton-Raphson法による平方根近似
- **精度**: 近似計算のため若干の誤差あり（スケール: 10000）
- **本番環境**: 使用可能

### Python高精度（compare_similarity_accuracy.py）
- **目的**: リファレンス実装として高精度な結果を提供
- **計算方式**: NumPy浮動小数点演算（64bit float）
- **精度**: 高精度（真値に最も近い）
- **本番環境**: 使用不可（開発環境での精度検証のみ）

### 比較することで得られる情報
1. **ZKP近似の精度**: どの程度の誤差があるか
2. **実用性の検証**: 近似誤差が許容範囲内か
3. **サブキャリア選択の一致性**: 上位5つのサブキャリアが一致するか

## 結果の保存

全てのスクリプトは結果を`zkp/results/`ディレクトリに保存します：

```
zkp/results/
├── similarities_2024-01-14T12-00-00-000Z.json    # ZKP結果（証明付き）
├── py_similarities_2024-01-14T12-02-00-000Z.json # Python結果（比較用）
└── js_similarities_2024-01-14T12-01-00-000Z.json # JavaScript結果（デバッグ用、オプション）
```

### ZKP結果ファイル（similarities_*.json）
```json
{
  "timestamp": "2024-01-14T12:00:00.000Z",
  "num_subcarriers": 245,
  "num_freq_points": 25,
  "zkp_results": {
    "top_5": [...],
    "min_similarity": 0.654321,
    "min_index": 123,
    "all_similarities": [...]
  },
  "proof_valid": true,
  "input_data": {
    "referenceMatrix": [...],
    "candidateMatrix": [...]
  }
}
```

### Python結果ファイル（py_similarities_*.json）
```json
{
  "timestamp": "2024-01-14T12:02:00.000Z",
  "num_subcarriers": 245,
  "num_freq_points": 25,
  "calculation_time_ms": 12.34,
  "statistics": {
    "mean": 0.987654,
    "median": 0.991234,
    "std_dev": 0.012345,
    "min": 0.654321,
    "max": 0.999876,
    "q25": 0.976543,
    "q75": 0.992345
  },
  "top_5_lowest": [...],
  "all_similarities": [...],
  "all_details": [...]
}
```

## データ形式

入力データ（カスタムデータファイルを使用する場合）：

```json
{
  "referenceMatrix": [
    [1000, 1005, 1010, ...],  // 周波数ポイント0, 245サブキャリア
    [1002, 1007, 1012, ...],  // 周波数ポイント1
    ...                        // 25周波数ポイント
  ],
  "candidateMatrix": [
    [1001, 1006, 1011, ...],
    [1003, 1008, 1013, ...],
    ...
  ]
}
```

- `referenceMatrix`: 25 x 245 の行列（ベースCSI）
- `candidateMatrix`: 25 x 245 の行列（取得CSI）

## バックエンドAPI

バックエンドのZKPServiceに新しいメソッドが追加されています：

```python
# Python (backend/app/services/zkp_service.py)
zkp_service = ZKPService()

# 上位N個の低類似度サブキャリアを取得
result = zkp_service.select_top_n_lowest_similarity_subcarriers(
    reference_matrix=reference_matrix,
    candidate_matrix=candidate_matrix,
    top_n=5  # デフォルト: 5
)

# 結果
# {
#   "top_n_indices": [123, 234, 45, 178, 89],
#   "top_n_similarities": [0.654321, 0.678901, ...],
#   "all_similarities": [0.987654, 0.991234, ...],
#   "lowest_index": 123,
#   "lowest_similarity": 0.654321,
#   "num_subcarriers": 245
# }
```

## トラブルシューティング

### ZKP証明生成エラー
```bash
❌ WASM file not found
```
→ 回路をコンパイルしてください：
```bash
npm run compile:full_similarity
npm run setup:full_similarity
```

### Python実行エラー
```bash
ModuleNotFoundError: No module named 'numpy'
```
→ NumPyをインストールしてください：
```bash
pip install numpy
```

## 実際の使用例

### 例1: ZKP精度検証（推奨）

```bash
cd zkp

# ステップ1: ZKP回路で証明を生成
npm run prove:all_subcarriers

# 出力:
# 📉 Top 5 Lowest Similarities (ZKP Circuit):
#   1. Subcarrier 123: 0.654321
#   2. Subcarrier 234: 0.678901
#   ...
# ✅ PROOF VERIFIED SUCCESSFULLY!
# 💾 Results saved to: zkp/results/similarities_2024-01-14T12-00-00-000Z.json

# ステップ2: Python高精度計算で比較
npm run compare:accuracy

# 出力:
# 📂 Loading input data from latest ZKP results: similarities_2024-01-14T12-00-00-000Z.json
# 🔍 Accuracy Comparison (Python High-Precision vs ZKP Circuit):
#   Mean Absolute Difference:   0.00001234
#   Max Absolute Difference:    0.00005678
#   ...
# 📊 Top 5 Lowest Similarities Comparison:
#   Rank | Python SC | Python Sim | ZKP SC    | ZKP Sim    | Diff
#   1    |       123 | 0.654321   |       123 | 0.654310   | 0.00001100
#   ...
```

### 例2: カスタムデータで検証

```bash
# 1. カスタムデータファイルを準備（JSON形式）
cat > custom_data.json << EOF
{
  "referenceMatrix": [[...], [...], ...],  # 25 x 245
  "candidateMatrix": [[...], [...], ...]   # 25 x 245
}
EOF

# 2. ZKP証明生成（カスタムデータ対応は今後実装予定）
# 現在はサンプルデータのみ対応

# 3. Pythonで直接比較
python3 scripts/compare_similarity_accuracy.py custom_data.json
```

### 例3: JavaScript直接計算（デバッグ用）

```bash
# ZKP不要の高速計算（精度検証なし）
npm run calc:similarities

# 出力: JavaScript直接計算の結果のみ表示
```

## 参考情報

- ZKP回路: `zkp/circuits/csi_full_similarity.circom`
- バックエンドサービス: `backend/app/services/zkp_service.py`
- プロジェクトドキュメント: `CLAUDE.md`
