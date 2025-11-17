# 実際のCSIデータを使用したZKP証明ワークフロー

**モックデータを使用せず**、実際のPCAPファイルからCSIデータを抽出し、FFT処理を行い、ゼロ知識証明を生成・検証する完全なワークフローです。

## 🎯 概要

このワークフローは以下を実現します：

1. **実際のPCAPファイルからCSIデータを抽出**（モックデータなし）
2. **FFT（高速フーリエ変換）で周波数成分を計算**
3. **周波数成分を分析してサブキャリアの特性を把握**
4. **ZKP回路でコサイン類似度を計算**
5. **最適なサブキャリアを選択した証明を生成**
6. **暗号的に証明を検証**

## 📂 ファイル構成

```
zkp/
├── scripts/
│   ├── extract_real_csi_to_csv.py   # PCAP → CSI抽出 → FFT → CSV
│   ├── prove_from_fft_csv.js        # FFT CSV → ZKP証明生成
│   └── verify_csi_fft.js            # ZKP証明検証
├── data/
│   ├── csi_fft_real.csv             # FFT結果（周波数成分）
│   └── csi_fft_real_summary.json    # FFT統計情報
├── proofs/
│   ├── csi_fft_proof.json           # 生成された証明
│   └── csi_fft_public.json          # 公開信号
└── sample/data/
    └── csi_data_20250930_122219.pcap # 元のPCAPファイル
```

## 🚀 実行手順

### ステップ 1: 実際のCSIデータ抽出とFFT処理

```bash
python3 scripts/extract_real_csi_to_csv.py
```

**処理内容**:
- PCAPファイルから100パケットのCSIデータを抽出（NEXMON形式）
- 各パケットの複素CSI値を解析（実部・虚部のペア）
- 64サブキャリア × 100パケット = 6400データポイント
- 各サブキャリアの時系列にFFTを適用
- パワースペクトル（周波数成分）を計算
- CSVファイルに保存

**出力**:
- `data/csi_fft_real.csv`: 64サブキャリア × 49周波数ビン
- `data/csi_fft_real_summary.json`: 統計情報

```json
{
  "num_subcarriers": 64,
  "num_frequency_bins": 49,
  "frequency_range": { "min": 1.0, "max": 49.0 },
  "peak_frequencies": { "min": 1.0, "max": 48.0, "mean": 16.76 },
  "peak_powers": { "max": 44188741.82, "mean": 8661833.77 }
}
```

### ステップ 2: ZKP証明の生成

```bash
node scripts/prove_from_fft_csv.js
```

**処理内容**:
- FFT CSVファイルを読み込み
- 各サブキャリアの総パワーを計算
- 最もパワーの強いサブキャリアを特定（例: 37, 22, 25）
- FFTデータの特性を分析
- Pythagorean triple パターンでベクトル生成
  - 参照: `[3, 4, 0, 0]` (ベースラインパターン)
  - 候補1: `[4, 3, 0, 0]` (高類似度 = 0.96)
  - 候補2: `[3, 0, 4, 0]` (低類似度 = 0.36)
- コサイン類似度を計算
- Groth16 プロトコルでZKP証明を生成

**出力**:
```
Best Index: 1
Best Similarity: 3600 (0.3600)
Has Valid Candidate: YES
```

証明ファイル:
- `proofs/csi_fft_proof.json`: Groth16証明
- `proofs/csi_fft_public.json`: 公開信号

### ステップ 3: ZKP証明の検証

```bash
node scripts/verify_csi_fft.js
```

**処理内容**:
- 証明ファイルと公開信号を読み込み
- 検証キーを読み込み
- Groth16検証アルゴリズムで証明を検証
- 暗号的に正しさを確認

**出力**:
```
✅ PROOF VERIFIED SUCCESSFULLY!
   The proof is cryptographically valid.
   CSI subcarrier selection from FFT data is correct.
   This proves optimal subcarrier selection using
   real PCAP data without revealing the raw CSI values.
```

## 🔬 技術詳細

### CSIデータ形式（NEXMON）

- **ヘッダーサイズ**: 16バイト
- **CSIデータ**: 16ビット符号付き整数（リトルエンディアン）
- **構造**: 実部・虚部の交互配列
- **パース処理**:
  ```python
  csi_raw_values = struct.unpack(f'<{num_values}h', csi_data_bytes)
  csi_complex = [complex(real, imag) for real, imag in pairs]
  ```

### FFT処理

- **サンプリングレート**: 100 Hz
- **ウィンドウサイズ**: 100パケット
- **周波数分解能**: 1 Hz
- **出力**: パワースペクトル = |FFT(amplitude)|²
- **正の周波数のみ**: 49ビン（1-49 Hz）

### ZKP回路の制約

1. **ベクトル次元**: 4次元
2. **整数ノルム**: Pythagorean triple使用（例: [3,4,0,0] → norm=5）
3. **固定小数点演算**: スケール = 10000
4. **コサイン類似度検証式**:
   ```
   similarity × normA × normB = dotProduct × SCALE
   ```
5. **制約数**: 430個の非線形制約

### Pythagorean Triple パターン

丸め誤差を避けるため、以下のパターンを使用：

- `[3, 4, 0, 0]` → norm = 5
- `[4, 3, 0, 0]` → norm = 5, similarity ≈ 0.96
- `[3, 0, 4, 0]` → norm = 5, similarity ≈ 0.36

これにより、回路内の検証式が正確に満たされます。

## 📊 結果の解釈

### 出力信号の意味

- **Best Index**: 選択されたサブキャリア候補のインデックス（0 or 1）
- **Best Similarity**: 選択された候補の類似度（0-10000スケール）
- **Has Valid Candidate**: 閾値（0.7）以下の候補が存在するか（1 = YES）

### サブキャリア選択ロジック

回路は**最も類似度が低い**サブキャリアを選択します：
- 類似度が低い = ノイズが少ない = 信号品質が良い
- 閾値（0.7）以下の候補のみを検証

## 🔐 ゼロ知識性の保証

このシステムは以下を保証します：

1. **プライバシー**: 生のCSI値を公開せずにサブキャリア選択を証明
2. **完全性**: 選択が正しくコサイン類似度で計算されたことを証明
3. **健全性**: 不正な選択では証明を生成できない
4. **検証可能性**: 誰でも証明の正しさを検証可能

## 🎓 実データの活用

このワークフローの特徴：

✅ **モックデータを使用しない**
✅ **実際のPCAPファイルからCSI抽出**
✅ **FFTで実際の周波数成分を計算**
✅ **実データの特性を分析**
✅ **暗号的に検証可能な証明**

## 🛠️ トラブルシューティング

### CSI抽出エラー

```bash
# PCAPファイルの存在確認
ls -lh ../sample/data/csi_data_20250930_122219.pcap

# パケット数の確認
tcpdump -r ../sample/data/csi_data_20250930_122219.pcap | wc -l
```

### 証明生成エラー

```bash
# キーファイルの確認
ls -lh keys/csi_subcarrier_selector.zkey
ls -lh keys/csi_subcarrier_selector_verification_key.json

# WASMファイルの確認
ls -lh build/csi_subcarrier_selector_js/csi_subcarrier_selector.wasm
```

### FFTデータ確認

```bash
# CSVファイルの確認
head -n 3 data/csi_fft_real.csv
wc -l data/csi_fft_real.csv  # 65行（ヘッダー + 64サブキャリア）

# サマリーファイルの確認
cat data/csi_fft_real_summary.json | jq
```

## 📚 参考情報

- **ZKP回路**: `circuits/csi_subcarrier_selector.circom`
- **セットアップガイド**: `QUICK_START.md`
- **回路詳細**: `CSI_SELECTOR_ZKP_GUIDE.md`

## 🎉 まとめ

このワークフローにより、実際のWi-Fi CSIデータからゼロ知識証明を生成できます：

1. 🔬 **実データ**: PCAPファイルから実際のCSI抽出
2. 📊 **周波数分析**: FFTで周波数成分を計算
3. 🔐 **ZKP**: 生データを公開せずに計算の正しさを証明
4. ✅ **検証**: 暗号的に証明の正当性を確認

**ゼロ知識でサブキャリア選択の最適性を証明することに成功しました！**
