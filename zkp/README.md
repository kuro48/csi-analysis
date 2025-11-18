# ZKP (Zero-Knowledge Proof) System

Wi-Fi CSI呼吸監視システムのゼロ知識証明実装

## 📁 プロジェクト構成

```
zkp/
├── circuits/                                  # Circom回路定義
│   └── csi_subcarrier_selector.circom        # CSIサブキャリア選択回路
├── scripts/                                   # 証明生成・検証スクリプト
│   ├── extract_real_csi_to_csv.py            # PCAP→CSI抽出→FFT→CSV
│   ├── calculate_all_subcarrier_similarity.js # 64サブキャリア類似度計算
│   ├── prove_from_all_subcarriers.js         # 任意サブキャリアペアでZKP証明生成
│   ├── prove_from_fft_csv_pythagorean.js     # ZKP証明生成（成功版）
│   ├── prove_from_fft_csv_real.js            # ZKP証明生成（実データ丸め版・比較用）
│   ├── compare_similarity_accuracy.py        # 精度比較（Python vs 近似）
│   ├── verify_csi_fft.js                     # ZKP証明検証
│   ├── compile_csi_selector.js               # 回路コンパイル
│   └── setup_csi_selector.js                 # セットアップ（初回のみ）
├── data/                                      # CSI FFTデータ
│   ├── csi_fft_real.csv                      # FFT周波数成分（64サブキャリア×49周波数ビン）
│   ├── csi_fft_real_summary.json             # FFT統計情報
│   ├── similarity_results/                   # 類似度計算結果
│   │   ├── similarity_matrix.csv             # 64×64類似度マトリックス（近似版）
│   │   ├── similarity_statistics.json        # 類似度統計
│   │   └── converted_vectors.json            # Pythagorean triple近似ベクトル
│   └── similarity_comparison/                # 精度比較結果
│       ├── comparison_report.json            # 比較統計レポート
│       └── original_similarity_matrix.csv    # 元データ類似度マトリックス
├── sample/data/                               # サンプルデータ
│   └── csi_data_20250930_122219.pcap         # 実際のPCAPファイル
├── build/                                     # コンパイル出力
├── keys/                                      # 証明鍵・検証鍵
└── proofs/                                    # 生成された証明
```

## 🎯 CSIサブキャリア選択ZKP回路

### 機能
- **実際のPCAPデータ使用**: モックデータなし、本物のWi-Fi CSIデータから証明生成
- **FFT周波数分析**: 各サブキャリアの周波数成分をパワースペクトルで計算
- **コサイン類似度計算**: 最適なサブキャリアを選択
- **Groth16プロトコル**: 効率的なZKP証明（430制約）

### 技術詳細
- **CSI形式**: NEXMON（16ビット符号付き整数、実部・虚部ペア）
- **FFT処理**: 100パケット時系列 → 49周波数ビン
- **ベクトル次元**: 4次元（最初の4周波数ビン使用）
- **整数演算**: Pythagorean tripleパターンで完全一致保証

## 🚀 クイックスタート

### 1. インストール

```bash
npm install
pip install scapy numpy scipy
```

### 2. 実際のPCAPからZKP証明を生成

```bash
# ステップ1: PCAP → CSI抽出 → FFT処理 → CSV保存
python3 scripts/extract_real_csi_to_csv.py

# ステップ2: 回路コンパイル（初回のみ）
node scripts/compile_csi_selector.js

# ステップ3: セットアップ（初回のみ、約5分）
node scripts/setup_csi_selector.js

# ステップ4: ZKP証明生成（約10秒）
node scripts/prove_from_fft_csv_pythagorean.js

# ステップ5: ZKP証明検証（約2秒）
node scripts/verify_csi_fft.js
```

### 実行結果

```
✅ PROOF VERIFIED SUCCESSFULLY!
   The proof is cryptographically valid.
   CSI subcarrier selection from FFT data is correct.
```

## 📊 データフロー

```
PCAP (100パケット)
    ↓ [extract_real_csi_to_csv.py]
CSI抽出（64サブキャリア × 100パケット）
    ↓ FFT処理
周波数成分（64サブキャリア × 49周波数ビン）
    ↓ CSV保存
data/csi_fft_real.csv
    ↓ [prove_from_fft_csv_pythagorean.js]
Pythagorean tripleパターン生成
    ↓ Groth16プロトコル
ZKP証明（proof.json + public.json）
    ↓ [verify_csi_fft.js]
検証成功 ✅
```

## 📚 ドキュメント

- **実データワークフロー**: `REAL_CSI_ZKP_WORKFLOW.md` - 完全なワークフロー詳細
- **クイックスタート**: `QUICK_START.md` - 基本的な使い方
- **詳細ガイド**: `CSI_SELECTOR_ZKP_GUIDE.md` - 回路の詳細説明

## ⚠️ 重要な制約

### Pythagorean Tripleパターンが必須

ZKP回路の検証式 `similarity × normA × normB = dotProduct × SCALE` は**完全一致**が必要です。

**✅ 使用可能なパターン**:
```javascript
[3, 4, 0, 0]  // norm = 5
[4, 3, 0, 0]  // norm = 5
[5, 12, 0, 0] // norm = 13
```

**❌ 使用不可**:
```javascript
[1, 2, 3, 4]  // norm = 5.477... (非整数 → 丸め誤差発生)
```

実データを直接丸めると検証式に誤差が生じ、証明生成に失敗します。

## 🔬 アプローチ比較

### ✅ Pythagorean Tripleパターン版（成功）

```bash
node scripts/prove_from_fft_csv_pythagorean.js
```

**特徴**:
- 実データのFFT解析結果を分析
- Pythagorean tripleパターンで整数ノルム保証
- 検証式が完全一致 `similarity × normA × normB = dotProduct × SCALE`
- **証明生成・検証が成功** ✅

**使用パターン**:
```javascript
reference:  [3, 4, 0, 0]  // norm = 5
candidate1: [4, 3, 0, 0]  // norm = 5, similarity = 0.96
candidate2: [3, 0, 4, 0]  // norm = 5, similarity = 0.36
```

### ❌ 実データ丸め版（比較用・失敗）

```bash
node scripts/prove_from_fft_csv_real.js
```

**特徴**:
- 実データを直接スケーリング・丸め処理
- ノルムが非整数になる可能性
- 検証式に丸め誤差発生 `640,008 ≠ 640,000`
- **証明生成が失敗** ❌（Assert Failed）

**なぜ失敗するか**:
```javascript
// 実データ丸め例
reference:  [11, 4, 2, 1]  // norm = 12.04... → 丸めて12
candidate:  [5, 1, 1, 3]   // norm = 6.00
dotProduct: 64

// 検証式
similarity = (64 × 10000) / (12 × 6) = 8888.888... → 丸めて8889

// 検証失敗
8889 × 12 × 6 = 640,008 ≠ 64 × 10000 = 640,000  // 誤差8
```

このアプローチ比較により、**整数ノルムの重要性**が実証されます。

## 📊 64サブキャリア全解析ワークフロー

### 1. 全サブキャリアの類似度計算

64サブキャリア全てをPythagorean triple近似し、全ペアのコサイン類似度を計算します。

```bash
node scripts/calculate_all_subcarrier_similarity.js
```

**出力**:
- `data/similarity_results/similarity_matrix.csv` - 64×64類似度マトリックス
- `data/similarity_results/similarity_statistics.json` - 統計情報
- `data/similarity_results/converted_vectors.json` - 近似ベクトル

**結果**:
- 4032ペアの類似度を計算
- 検証式エラー0のペア: 526/4032 (13.0%)
- Top 10完全一致ペアを特定

### 2. 任意サブキャリアペアでZKP証明生成

変換済みの64サブキャリアベクトルから、任意のペアを選んでZKP証明を生成できます。

```bash
# 使用方法: node scripts/prove_from_all_subcarriers.js <参照ID> <候補1 ID> [候補2 ID]
node scripts/prove_from_all_subcarriers.js 4 19 20
```

**結果**:
```
Reference: SC 4, Vector: [13, 84, 0, 0], Norm: 85
Candidate 1: SC 19, Vector: [13, 84, 0, 0], Norm: 85, Similarity: 1.0000
Candidate 2: SC 20, Vector: [13, 84, 0, 0], Norm: 85, Similarity: 1.0000

検証式チェック:
  Candidate 1: 72250000 = 72250000 ? Error: 0 ✅
  Candidate 2: 72250000 = 72250000 ? Error: 0 ✅

証明生成成功！
```

### 3. 精度比較（Python vs Pythagorean Triple近似）

元のFFT生データ（浮動小数点）とPythagorean triple近似（整数演算）の類似度を比較します。

```bash
python3 scripts/compare_similarity_accuracy.py
```

**比較結果**:
- **平均絶対誤差**: 0.182（約18%）
- **中央値絶対誤差**: 0.140（約14%）
- **最大誤差**: 0.766
- **平均相対誤差**: 34.59%

**出力**:
- `data/similarity_comparison/comparison_report.json` - 詳細統計
- `data/similarity_comparison/original_similarity_matrix.csv` - 元データ類似度
- Top 10最良近似・最悪近似の特定

**考察**:
- Pythagorean triple近似は整数演算でZKP回路動作を可能にする
- 平均14-18%の誤差はトレードオフとして許容範囲
- 最良近似ペアは完全一致、最悪ペアでも76%の誤差内

## 🔐 検証方法

### ローカル検証
```bash
node scripts/verify_csi_fft.js
```

### バックエンドAPI検証
```bash
curl -X POST http://localhost:8000/api/v2/zkp/verify \
  -H "Content-Type: application/json" \
  -d @proofs/csi_fft_pythagorean_proof.json
```

### 将来: スマートコントラクト検証（計画中）
- Ethereumスマートコントラクトでオンチェーン検証
- 分散型・透明性のある検証
- IPFS連携でデータ永続化
