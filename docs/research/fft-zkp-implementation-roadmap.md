# 🔬 研究用FFT-ZKP実装ロードマップ

**作成日**: 2024-10-28
**バージョン**: 1.0
**ステータス**: 計画策定完了

---

## 目標設定

### 研究目的
1. **技術的実証**: ZKP回路でのFFT実装可能性の検証
2. **性能評価**: 制約数、証明生成時間、検証時間のベンチマーク
3. **学術貢献**: CSI呼吸解析×ZKP-FFTの新規性を論文化
4. **段階的アプローチ**: N=4 → N=8 → N=16へ段階的拡張

### 成果物
- ✅ 動作するFFT-ZKP回路（N=4, 8, 16）
- ✅ 性能ベンチマークデータ
- ✅ 研究論文（国内学会→国際学会）
- ✅ オープンソース実装（GitHub）

---

## 📅 実装スケジュール（12週間）

| Phase | 期間 | 内容 | 成果物 |
|-------|------|------|--------|
| **Phase 1** | Week 1-2 | 基礎理論学習と環境構築 | 環境セットアップ完了 |
| **Phase 2** | Week 3-4 | 超小規模FFT実装（N=4） | DFT-ZKP回路 |
| **Phase 3** | Week 5-7 | 小規模FFT実装（N=8） | Cooley-Tukey FFT回路 |
| **Phase 4** | Week 8-10 | 中規模FFT実装（N=16） | 最適化FFT回路 |
| **Phase 5** | Week 11 | 呼吸解析統合・ベンチマーク | 性能評価データ |
| **Phase 6** | Week 12+ | 論文執筆・発表準備 | 研究論文初稿 |

---

## Phase 1: 基礎理論学習と環境構築（Week 1-2）

### Week 1: 理論学習

#### 1.1 FFTアルゴリズムの復習
```bash
# 学習項目
□ DFT（離散フーリエ変換）の数学的定義
□ Cooley-Tukey FFTアルゴリズム
□ Butterfly操作の理解
□ ビット反転アドレッシング
□ 回転因子（Twiddle Factor）の計算
```

**推奨リソース**:
- 教科書: "Understanding Digital Signal Processing" (Richard Lyons)
- オンライン: [FFT Explained (YouTube)](https://www.youtube.com/results?search_query=fft+explained)

#### 1.2 ZKP回路設計の学習
```bash
# 学習項目
□ circomの基本文法（信号、制約、テンプレート）
□ 有限体演算の理解
□ 固定小数点演算の実装方法
□ circomlibのコンポーネント（Comparators, Mux等）
```

**推奨リソース**:
- [circom公式ドキュメント](https://docs.circom.io/)
- [circomlib GitHub](https://github.com/iden3/circomlib)

---

### Week 2: 環境構築とサンプル実装

#### 2.1 開発環境セットアップ
```bash
# 1. Rustツールチェーンのインストール
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# 2. circomのインストール
git clone https://github.com/iden3/circom.git
cd circom
cargo build --release
cargo install --path circom
circom --version  # 2.0.0以上を確認

# 3. ZKPプロジェクトのセットアップ
cd ~/csi-web-platform/zkp
npm install
```

#### 2.2 サンプル回路の動作確認
```bash
# 既存の呼吸検証回路をコンパイル・テスト
npm run compile
npm run setup
npm test

# 性能測定
time npm run prove
time npm run verify
```

#### 2.3 研究用ディレクトリ構成
```bash
zkp/
├── circuits/
│   ├── breathing_verifier.circom      # 既存（簡略検証）
│   ├── research/                      # 新規: 研究用FFT回路
│   │   ├── fft_n4.circom             # N=4 DFT
│   │   ├── fft_n8.circom             # N=8 FFT
│   │   ├── fft_n16.circom            # N=16 FFT
│   │   └── components/               # 共通コンポーネント
│   │       ├── complex_mul.circom    # 複素数乗算
│   │       ├── butterfly.circom      # Butterfly操作
│   │       └── twiddle_factor.circom # 回転因子
├── test/
│   └── research/                      # FFT回路テスト
│       ├── fft_n4.test.js
│       ├── fft_n8.test.js
│       └── benchmark.test.js         # 性能測定
├── scripts/
│   └── research/
│       └── benchmark.js              # ベンチマークスクリプト
└── docs/
    └── research/
        ├── implementation-notes.md   # 実装ノート
        └── benchmark-results.md      # 性能測定結果
```

---

## Phase 2: 超小規模FFT実装（N=4, DFT）（Week 3-4）

### Week 3: 基礎コンポーネントの実装

#### 3.1 複素数演算コンポーネント

**ファイル**: `zkp/circuits/research/components/complex_mul.circom`

```circom
pragma circom 2.0.0;

/**
 * 複素数乗算: (a + bi) × (c + di) = (ac - bd) + (ad + bc)i
 *
 * 固定小数点: 1000倍スケール（3桁精度）
 * 例: 1.234 → 1234
 */
template ComplexMul() {
    signal input a;  // 実部1
    signal input b;  // 虚部1
    signal input c;  // 実部2
    signal input d;  // 虚部2

    signal output real;
    signal output imag;

    // 中間信号
    signal ac;
    signal bd;
    signal ad;
    signal bc;

    ac <== a * c;
    bd <== b * d;
    ad <== a * d;
    bc <== b * c;

    // 固定小数点スケーリング（1000で除算）
    real <== (ac - bd) / 1000;
    imag <== (ad + bc) / 1000;
}
```

**テスト**: `zkp/test/research/complex_mul.test.js`
```javascript
const { expect } = require("chai");
const { wasm: wasm_tester } = require("circom_tester");

describe("ComplexMul", function () {
  let circuit;

  before(async () => {
    circuit = await wasm_tester("circuits/research/components/complex_mul.circom");
  });

  it("複素数乗算: (3+4i) × (1+2i) = -5+10i", async () => {
    const input = {
      a: 3000,  // 3.0 × 1000
      b: 4000,  // 4.0 × 1000
      c: 1000,  // 1.0 × 1000
      d: 2000   // 2.0 × 1000
    };

    const witness = await circuit.calculateWitness(input);

    // (3+4i) × (1+2i) = 3×1 - 4×2 + (3×2 + 4×1)i = -5 + 10i
    await circuit.assertOut(witness, {
      real: -5000,  // -5.0 × 1000
      imag: 10000   // 10.0 × 1000
    });
  });
});
```

#### 3.2 回転因子（Twiddle Factor）テーブル

**ファイル**: `zkp/circuits/research/components/twiddle_factor.circom`

```circom
pragma circom 2.0.0;

/**
 * 回転因子テーブル（N=4用）
 * W_4^k = e^(-2πik/4) = cos(-πk/2) - i×sin(-πk/2)
 *
 * k=0: W_4^0 = 1 + 0i
 * k=1: W_4^1 = 0 - 1i
 * k=2: W_4^2 = -1 + 0i
 * k=3: W_4^3 = 0 + 1i
 */
template TwiddleFactor4(k) {
    signal output real;
    signal output imag;

    // 固定小数点（1000倍スケール）
    if (k == 0) {
        real <== 1000;   // 1.0
        imag <== 0;
    } else if (k == 1) {
        real <== 0;
        imag <== -1000;  // -1.0i
    } else if (k == 2) {
        real <== -1000;  // -1.0
        imag <== 0;
    } else if (k == 3) {
        real <== 0;
        imag <== 1000;   // 1.0i
    }
}
```

---

### Week 4: N=4 DFT回路の実装

#### 4.1 DFT直接計算（FFTアルゴリズムではない）

**ファイル**: `zkp/circuits/research/fft_n4.circom`

```circom
pragma circom 2.0.0;

include "./components/complex_mul.circom";
include "./components/twiddle_factor.circom";

/**
 * N=4 DFT（直接計算版）
 *
 * X[k] = Σ(n=0 to 3) x[n] × W_4^(kn)
 *
 * 入力: 実数信号 x[0..3]（固定小数点 ×1000）
 * 出力: 周波数成分 X[0..3]のパワー |X[k]|^2
 */
template DFT4() {
    signal input x[4];        // 入力信号（実数のみ）
    signal output power[4];   // パワースペクトラム

    // 各周波数成分の実部・虚部
    signal X_real[4];
    signal X_imag[4];

    // k=0: DC成分（回転因子なし）
    X_real[0] <== x[0] + x[1] + x[2] + x[3];
    X_imag[0] <== 0;

    // k=1, 2, 3: 複素数演算
    component twiddle[3][4];  // k=1,2,3 × n=0,1,2,3
    component mul[3][4];

    for (var k = 1; k < 4; k++) {
        signal sum_real;
        signal sum_imag;
        signal partial_real[4];
        signal partial_imag[4];

        for (var n = 0; n < 4; n++) {
            // W_4^(k×n)の取得
            var kn = (k * n) % 4;
            twiddle[k-1][n] = TwiddleFactor4(kn);

            // x[n] × W_4^(kn)
            mul[k-1][n] = ComplexMul();
            mul[k-1][n].a <== x[n];
            mul[k-1][n].b <== 0;  // 入力は実数
            mul[k-1][n].c <== twiddle[k-1][n].real;
            mul[k-1][n].d <== twiddle[k-1][n].imag;

            partial_real[n] <== mul[k-1][n].real;
            partial_imag[n] <== mul[k-1][n].imag;
        }

        // Σ x[n] × W_4^(kn)
        X_real[k] <== partial_real[0] + partial_real[1] + partial_real[2] + partial_real[3];
        X_imag[k] <== partial_imag[0] + partial_imag[1] + partial_imag[2] + partial_imag[3];
    }

    // パワースペクトラム計算: |X[k]|^2 = real^2 + imag^2
    for (var k = 0; k < 4; k++) {
        power[k] <== (X_real[k] * X_real[k] + X_imag[k] * X_imag[k]) / 1000000;  // スケーリング調整
    }
}

component main {public [x]} = DFT4();
```

#### 4.2 テスト実装

**ファイル**: `zkp/test/research/fft_n4.test.js`

```javascript
const { expect } = require("chai");
const { wasm: wasm_tester } = require("circom_tester");

describe("DFT4", function () {
  this.timeout(100000);
  let circuit;

  before(async () => {
    circuit = await wasm_tester("circuits/research/fft_n4.circom");
  });

  it("DC信号（全て同じ値）", async () => {
    const input = {
      x: [1000, 1000, 1000, 1000]  // 全て1.0
    };

    const witness = await circuit.calculateWitness(input);

    // X[0] = 4.0（DC成分のみ）、X[1,2,3] = 0
    // パワー: X[0] = 16.0, X[1,2,3] = 0
    await circuit.checkConstraints(witness);
  });

  it("単一周波数信号", async () => {
    // sin(2πn/4) = [0, 1, 0, -1]（近似）
    const input = {
      x: [0, 1000, 0, -1000]
    };

    const witness = await circuit.calculateWitness(input);
    await circuit.checkConstraints(witness);

    // ピークはk=1付近に出現
  });

  it("実データ: CSI振幅サンプル", async () => {
    const input = {
      x: [1200, 1350, 1100, 1250]  // 実際のCSI振幅（スケール済み）
    };

    const witness = await circuit.calculateWitness(input);
    await circuit.checkConstraints(witness);
  });
});
```

#### 4.3 制約数とパフォーマンスの測定

```bash
# コンパイル
cd zkp
circom circuits/research/fft_n4.circom --r1cs --wasm --sym

# 制約数確認
snarkjs r1cs info build/research/fft_n4.r1cs

# テスト実行
npm test -- test/research/fft_n4.test.js

# ベンチマーク
node scripts/research/benchmark.js fft_n4
```

**期待される結果**:
- 制約数: ~500〜1,000
- 証明生成時間: <3秒
- 検証時間: <1秒

---

## Phase 3: 小規模FFT実装（N=8, Cooley-Tukey）（Week 5-7）

### Week 5: Butterfly操作の実装

#### 5.1 Butterfly基本コンポーネント

**ファイル**: `zkp/circuits/research/components/butterfly.circom`

```circom
pragma circom 2.0.0;

include "./complex_mul.circom";

/**
 * Cooley-Tukey Butterfly操作
 *
 * 入力:
 *   x0, x1: 入力信号（複素数）
 *   W: 回転因子（複素数）
 *
 * 出力:
 *   y0 = x0 + W × x1
 *   y1 = x0 - W × x1
 */
template Butterfly() {
    // 入力
    signal input x0_real, x0_imag;
    signal input x1_real, x1_imag;
    signal input W_real, W_imag;

    // 出力
    signal output y0_real, y0_imag;
    signal output y1_real, y1_imag;

    // W × x1を計算
    component mul = ComplexMul();
    mul.a <== W_real;
    mul.b <== W_imag;
    mul.c <== x1_real;
    mul.d <== x1_imag;

    signal Wx1_real <== mul.real;
    signal Wx1_imag <== mul.imag;

    // y0 = x0 + W×x1
    y0_real <== x0_real + Wx1_real;
    y0_imag <== x0_imag + Wx1_imag;

    // y1 = x0 - W×x1
    y1_real <== x0_real - Wx1_real;
    y1_imag <== x0_imag - Wx1_imag;
}
```

#### 5.2 N=8用回転因子テーブル

**ファイル**: `zkp/circuits/research/components/twiddle_factor_n8.circom`

```circom
pragma circom 2.0.0;

/**
 * N=8用回転因子テーブル
 * W_8^k = e^(-2πik/8) = cos(-πk/4) - i×sin(-πk/4)
 *
 * k=0: (1.000, 0.000)
 * k=1: (0.707, -0.707)
 * k=2: (0.000, -1.000)
 * k=3: (-0.707, -0.707)
 * k=4: (-1.000, 0.000)
 * k=5: (-0.707, 0.707)
 * k=6: (0.000, 1.000)
 * k=7: (0.707, 0.707)
 */
template TwiddleFactor8(k) {
    signal output real;
    signal output imag;

    // 固定小数点（1000倍スケール）
    // √2/2 ≈ 0.707 → 707

    if (k == 0) {
        real <== 1000; imag <== 0;
    } else if (k == 1) {
        real <== 707; imag <== -707;
    } else if (k == 2) {
        real <== 0; imag <== -1000;
    } else if (k == 3) {
        real <== -707; imag <== -707;
    } else if (k == 4) {
        real <== -1000; imag <== 0;
    } else if (k == 5) {
        real <== -707; imag <== 707;
    } else if (k == 6) {
        real <== 0; imag <== 1000;
    } else if (k == 7) {
        real <== 707; imag <== 707;
    }
}
```

---

### Week 6-7: N=8 FFT完全実装

#### 6.1 Cooley-Tukey FFTアルゴリズム

**ファイル**: `zkp/circuits/research/fft_n8.circom`

```circom
pragma circom 2.0.0;

include "./components/butterfly.circom";
include "./components/twiddle_factor_n8.circom";

/**
 * N=8 Cooley-Tukey FFT
 *
 * 3段のButterfly操作:
 *   Stage 1: 4組のButterfly（stride=4）
 *   Stage 2: 4組のButterfly（stride=2）
 *   Stage 3: 4組のButterfly（stride=1）
 */
template FFT8() {
    signal input x[8];        // 入力信号（実数）
    signal output power[8];   // パワースペクトラム

    // 中間ステージの信号
    signal stage0_real[8], stage0_imag[8];
    signal stage1_real[8], stage1_imag[8];
    signal stage2_real[8], stage2_imag[8];
    signal stage3_real[8], stage3_imag[8];

    // Stage 0: 入力（実数を複素数に変換）
    for (var i = 0; i < 8; i++) {
        stage0_real[i] <== x[i];
        stage0_imag[i] <== 0;
    }

    // Stage 1: Butterfly (stride=4)
    component butterfly1[4];
    component twiddle1[4];

    for (var i = 0; i < 4; i++) {
        var k = i;  // 回転因子インデックス
        twiddle1[i] = TwiddleFactor8(k * 0);  // Stage 1はW^0のみ

        butterfly1[i] = Butterfly();
        butterfly1[i].x0_real <== stage0_real[i];
        butterfly1[i].x0_imag <== stage0_imag[i];
        butterfly1[i].x1_real <== stage0_real[i + 4];
        butterfly1[i].x1_imag <== stage0_imag[i + 4];
        butterfly1[i].W_real <== twiddle1[i].real;
        butterfly1[i].W_imag <== twiddle1[i].imag;

        stage1_real[i] <== butterfly1[i].y0_real;
        stage1_imag[i] <== butterfly1[i].y0_imag;
        stage1_real[i + 4] <== butterfly1[i].y1_real;
        stage1_imag[i + 4] <== butterfly1[i].y1_imag;
    }

    // Stage 2: Butterfly (stride=2)
    component butterfly2[4];
    component twiddle2[4];

    // ... 同様に実装 ...

    // Stage 3: Butterfly (stride=1)
    component butterfly3[4];
    component twiddle3[4];

    // ... 同様に実装 ...

    // パワースペクトラム計算
    for (var k = 0; k < 8; k++) {
        power[k] <== (stage3_real[k] * stage3_real[k] + stage3_imag[k] * stage3_imag[k]) / 1000000;
    }
}

component main {public [x]} = FFT8();
```

#### 6.2 テストとベンチマーク

**ファイル**: `zkp/test/research/fft_n8.test.js`

```javascript
const { expect } = require("chai");
const { wasm: wasm_tester } = require("circom_tester");

describe("FFT8", function () {
  this.timeout(300000);  // 5分タイムアウト
  let circuit;

  before(async () => {
    circuit = await wasm_tester("circuits/research/fft_n8.circom");
  });

  it("インパルス応答テスト", async () => {
    const input = {
      x: [1000, 0, 0, 0, 0, 0, 0, 0]  // インパルス
    };

    const witness = await circuit.calculateWitness(input);

    // 全周波数成分が等しくなる
    await circuit.checkConstraints(witness);
  });

  it("実CSIデータテスト", async () => {
    const input = {
      x: [1200, 1350, 1100, 1250, 1180, 1320, 1150, 1280]
    };

    const witness = await circuit.calculateWitness(input);
    await circuit.checkConstraints(witness);
  });
});
```

**ベンチマーク測定**:
```bash
node scripts/research/benchmark.js fft_n8
```

**期待される結果**:
- 制約数: ~5,000〜10,000
- 証明生成時間: ~10〜30秒
- 検証時間: <2秒

---

## Phase 4: 中規模FFT実装（N=16）（Week 8-10）

### 同様のアプローチでN=16に拡張

- 4段のButterfly操作
- 回転因子テーブルの拡張（16要素）
- ビット反転アドレッシングの実装
- 最適化技術の適用

**推定性能**:
- 制約数: ~20,000〜30,000
- 証明生成時間: ~60〜120秒

**実装ファイル**:
- `zkp/circuits/research/fft_n16.circom`
- `zkp/circuits/research/components/twiddle_factor_n16.circom`
- `zkp/test/research/fft_n16.test.js`

---

## Phase 5: 呼吸解析統合とベンチマーク（Week 11）

### 5.1 CSI呼吸データでの実験

**ファイル**: `backend/experiments/zkp_fft_experiment.py`

```python
import numpy as np
from app.services.zkp_service import ZKPService

# 実CSIデータでFFT-ZKP実験
csi_data = load_real_csi_data()  # 実データ読み込み

# N=8でダウンサンプリング
csi_downsampled = downsample(csi_data, target_n=8)

# ZKP-FFT実行
zkp_service = ZKPService()
proof = zkp_service.generate_proof_fft_n8(csi_downsampled)

# ベンチマーク
measure_performance(proof)
```

### 5.2 性能比較表の作成

| 手法 | サンプル数 | 制約数 | 証明時間 | 検証時間 | 精度 |
|-----|-----------|--------|---------|---------|------|
| ハイブリッド（現行） | 64 | ~10,000 | <10秒 | <1秒 | 高 |
| ZKP-FFT N=4 | 4 | ~1,000 | <5秒 | <1秒 | 低 |
| ZKP-FFT N=8 | 8 | ~5,000 | ~30秒 | <2秒 | 中 |
| ZKP-FFT N=16 | 16 | ~30,000 | ~120秒 | <2秒 | 中 |

### 5.3 精度評価

**Python FFTとの比較実験**:

```python
import numpy as np

# 実CSIデータ
csi_data = [1200, 1350, 1100, 1250, 1180, 1320, 1150, 1280]

# Python FFT（基準）
python_fft = np.fft.fft(csi_data)
python_power = np.abs(python_fft) ** 2

# ZKP-FFT結果（snarkjsから取得）
zkp_power = get_zkp_fft_power(csi_data)

# 誤差計算
error = np.abs(python_power - zkp_power) / python_power * 100
print(f"Average error: {np.mean(error):.2f}%")
```

**目標精度**: 誤差<5%

---

## Phase 6: 論文執筆と発表（Week 12+）

### 6.1 論文構成

**タイトル（仮）**: "Zero-Knowledge Proof-based FFT for Privacy-Preserving CSI Respiratory Monitoring"

**構成**:

1. **Abstract**
   - CSI呼吸監視とプライバシー課題
   - ZKP-FFTの提案
   - 主な貢献と成果

2. **Introduction**
   - 背景: 非接触呼吸監視の重要性
   - 課題: プライバシー保護と計算検証
   - 貢献: FFT-ZKP統合の実証

3. **Related Work**
   - CSI応用研究
   - ZKP医療応用
   - FFT実装の先行研究

4. **Proposed Method**
   - FFT-ZKP回路設計
   - Cooley-Tukey アルゴリズムの回路化
   - 固定小数点演算の工夫

5. **Implementation**
   - N=4, 8, 16の段階的実装
   - 制約数の最適化技術
   - テストとデバッグ手法

6. **Evaluation**
   - 性能ベンチマーク（制約数、証明時間）
   - 精度評価（Python FFTとの比較）
   - 実CSIデータでの実験結果

7. **Discussion**
   - 実用性の評価
   - スケーラビリティの課題
   - 今後の改善方向

8. **Conclusion**
   - 主要な貢献の要約
   - 将来展望

### 6.2 発表計画

**国内学会**:
- 電子情報通信学会（IEICE）総合大会
- 情報処理学会（IPSJ）全国大会
- センサネットワーク研究会

**国際学会（査読付き）**:
- ACM CCS (Computer and Communications Security)
- USENIX Security
- IEEE S&P (Security and Privacy)

**研究会・ワークショップ**:
- Workshop on Privacy-Preserving Machine Learning
- ZKProof Workshop

### 6.3 オープンソース公開

**GitHubリポジトリ構成**:
```
csi-zkp-fft/
├── README.md
├── LICENSE (MIT or Apache 2.0)
├── circuits/
│   ├── fft_n4.circom
│   ├── fft_n8.circom
│   ├── fft_n16.circom
│   └── components/
├── test/
├── scripts/
├── docs/
│   ├── implementation-guide.md
│   ├── benchmark-results.md
│   └── paper.pdf
└── examples/
    └── csi_breathing_example.py
```

---

## 📊 成功指標（KPI）

| 指標 | 目標値 | 測定方法 | 評価基準 |
|-----|--------|---------|---------|
| **FFT回路実装** | N=4, 8, 16 | 動作確認 | 全テスト合格 |
| **制約数** | N=8で<10,000 | r1cs info | Groth16実用範囲内 |
| **証明生成時間** | N=8で<60秒 | ベンチマーク | 実用的速度 |
| **検証時間** | <5秒 | ベンチマーク | オンチェーン可能 |
| **精度** | 誤差<5% | Python FFT比較 | 実用精度 |
| **論文投稿** | 1本以上 | 査読投稿 | 採択目標 |
| **GitHub公開** | スター>50 | リポジトリ | コミュニティ貢献 |

---

## 📝 実装チェックリスト

### Phase 1: 基礎（Week 1-2）
- [ ] FFTアルゴリズム学習完了
- [ ] circom基礎学習完了
- [ ] 環境構築完了（Rust, circom, snarkjs）
- [ ] サンプル回路動作確認
- [ ] 研究用ディレクトリ構成作成

### Phase 2: N=4 DFT（Week 3-4）
- [ ] ComplexMul実装・テスト
- [ ] TwiddleFactor実装・テスト
- [ ] DFT4回路実装
- [ ] テスト全合格
- [ ] ベンチマーク測定
- [ ] 実装ノート作成

### Phase 3: N=8 FFT（Week 5-7）
- [ ] Butterfly実装・テスト
- [ ] TwiddleFactor8実装
- [ ] FFT8回路実装
- [ ] テスト全合格
- [ ] ベンチマーク測定
- [ ] 性能分析レポート作成

### Phase 4: N=16 FFT（Week 8-10）
- [ ] TwiddleFactor16実装
- [ ] FFT16回路実装
- [ ] 最適化適用
- [ ] テスト全合格
- [ ] ベンチマーク測定
- [ ] 性能比較表完成

### Phase 5: 統合実験（Week 11）
- [ ] 実CSIデータ実験
- [ ] Python FFTとの精度比較
- [ ] 性能ベンチマーク完全版
- [ ] 実験結果ドキュメント作成

### Phase 6: 論文（Week 12+）
- [ ] 論文初稿完成
- [ ] 査読投稿
- [ ] 発表資料作成
- [ ] GitHub公開
- [ ] README・ドキュメント整備

---

## 🔬 研究的貢献

### 新規性

1. **ZKP-FFT統合の実証**: FFTアルゴリズムのZKP回路化の実装例
2. **医療IoTへの応用**: CSI呼吸監視でのプライバシー保護手法
3. **段階的拡張手法**: N=4 → 8 → 16への実用的実装アプローチ
4. **性能評価**: 制約数・証明時間・精度の包括的ベンチマーク

### 期待される学術的インパクト

- ZKP応用範囲の拡大（医療・IoT分野）
- プライバシー保護信号処理の新手法
- CSI応用研究への貢献
- オープンソース実装による再現性確保

---

## 📚 参考文献（予定）

### ZKP関連
- Ben-Sasson et al., "SNARKs for C: Verifying Program Executions Succinctly and in Zero Knowledge"
- Groth, "On the Size of Pairing-based Non-interactive Arguments"
- circom/snarkjs公式ドキュメント

### FFT実装
- Cooley & Tukey, "An Algorithm for the Machine Calculation of Complex Fourier Series"
- Lyons, "Understanding Digital Signal Processing"

### CSI応用
- Wang et al., "RT-Fall: A Real-Time and Contactless Fall Detection System with Commodity WiFi Devices"
- CSI呼吸監視関連の最新論文

---

## 🎯 次のステップ

1. **Phase 1開始**: 環境構築とFFT理論学習
2. **週次進捗会議**: 毎週金曜に進捗報告
3. **実装ノート**: 日々の実装内容を記録
4. **定期ベンチマーク**: 各Phase終了時に性能測定

このロードマップに従って、段階的にFFT-ZKP実装を進め、研究成果として論文発表できる水準を目指します。

---

**最終更新日**: 2024-10-28
**次回レビュー**: Phase 1完了時（Week 2終了時）
