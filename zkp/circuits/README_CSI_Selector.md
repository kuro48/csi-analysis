# CSIサブキャリア選択回路 - 技術ドキュメント

## 概要

このドキュメントでは、Wi-Fi CSI（Channel State Information）サブキャリア選択のためのゼロ知識証明回路について説明します。この回路は、コサイン類似度計算を用いて最適なサブキャリアペアを選択し、プライバシー保護とリアルタイム処理を両立させます。

## 目次

1. [技術的背景](#技術的背景)
2. [回路設計](#回路設計)
3. [数学的基礎](#数学的基礎)
4. [実装詳細](#実装詳細)
5. [使用方法](#使用方法)
6. [パフォーマンス最適化](#パフォーマンス最適化)

---

## 技術的背景

### 課題

Wi-Fi CSI測定では、複数のサブキャリア(周波数チャネル)から呼吸信号を抽出します。しかし、全てのサブキャリアが等しく有用というわけではありません:

- **ノイズの多いサブキャリア**: 環境ノイズや干渉の影響を受けやすい
- **信号品質の変動**: 時間経過や環境変化により最適なサブキャリアが変化
- **計算コスト**: 全サブキャリアを処理するとリアルタイム性が損なわれる

### 解決アプローチ

**コサイン類似度**を用いて、参照パターンとの類似性が高いサブキャリアを動的に選択:

```
cos_sim(A, B) = (A·B) / (||A|| × ||B||)
              = Σ(Ai × Bi) / (√Σ(Ai²) × √Σ(Bi²))
```

**ゼロ知識証明**により、選択ロジックの正当性を証明しつつ生データを秘匿:
- プライバシー: 生CSIデータを公開せずに計算結果のみ検証可能
- 透明性: 選択アルゴリズムの正当性を数学的に保証
- 効率性: 固定小数点演算による高速計算

---

## 回路設計

### アーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│              CSISubcarrierSelector                     │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐                   │
│  │ Reference    │  │ Candidate 1  │                   │
│  │ CSI Vector   │  │ CSI Vector   │                   │
│  └──────┬───────┘  └──────┬───────┘                   │
│         │                  │                            │
│         v                  v                            │
│  ┌──────────────────────────────────┐                  │
│  │  CosineSimilarityVerified        │                  │
│  │                                   │                  │
│  │  1. DotProduct(A, B)             │                  │
│  │  2. VectorNorm(A), VectorNorm(B) │                  │
│  │  3. Verify: sim × ||A|| × ||B||  │                  │
│  │            === dotProduct × SCALE│                  │
│  └──────────────┬───────────────────┘                  │
│                 │                                       │
│                 v                                       │
│  ┌──────────────────────────────────┐                  │
│  │  Threshold Check (>= 0.7)        │                  │
│  └──────────────┬───────────────────┘                  │
│                 │                                       │
│                 v                                       │
│  ┌──────────────────────────────────┐                  │
│  │  Max Similarity Selection        │                  │
│  │  → Output: bestIndex             │                  │
│  └──────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────┘
```

### コンポーネント構成

#### 1. `VectorNorm(N)`
- **入力**: N次元ベクトル
- **出力**: ノルムの二乗 `||V||²`
- **機能**: ベクトルのノルム計算（平方根は witness 側で計算）

#### 2. `DotProduct(N)`
- **入力**: 2つのN次元ベクトル
- **出力**: 内積 `A·B`
- **機能**: ベクトル内積計算

#### 3. `CosineSimilarityVerified(N, SCALE)`
- **入力**:
  - ベクトルA, B
  - ノルムA, B (witness計算)
  - 類似度 (witness計算)
- **出力**:
  - 検証済み類似度
  - 有効性フラグ
- **機能**: コサイン類似度の計算と検証

#### 4. `CSISubcarrierSelector(N, M, SCALE, THRESHOLD)`
- **入力**:
  - 参照CSIベクトル
  - M個の候補CSIベクトル
  - witness: ノルム、類似度
- **出力**:
  - 最適候補のインデックス
  - 最大類似度
  - 有効性フラグ
- **機能**: 複数候補から最適サブキャリアを選択

---

## 数学的基礎

### コサイン類似度の特性

コサイン類似度は、ベクトルの角度に基づく類似性指標です:

**範囲**: `[-1, 1]`
- `1`: 完全に同一方向 (同一パターン)
- `0`: 直交 (無関係)
- `-1`: 完全に反対方向

**利点**:
- **スケール不変**: ベクトルの大きさに依存しない
- **方向性重視**: パターンの形状を評価
- **計算効率**: 内積とノルムのみで計算可能

### 固定小数点演算

Circomは整数演算のみをサポートするため、固定小数点表現を使用:

**スケーリングファクター**: `SCALE = 10^4 = 10000`

| 実数値 | 固定小数点表現 |
|--------|----------------|
| 0.0    | 0              |
| 0.5    | 5000           |
| 0.7    | 7000           |
| 1.0    | 10000          |

**変換式**:
```
固定小数点 = 実数 × SCALE
実数 = 固定小数点 / SCALE
```

### 数値精度と誤差

**精度**:
- 小数点以下4桁の精度
- 類似度範囲: `0.0000 〜 1.0000`

**誤差要因**:
1. **固定小数点丸め**: ±0.0001程度
2. **整数除算**: ±0.0001程度
3. **累積誤差**: N次元で最大 ±0.001程度

**誤差対策**:
- 閾値に余裕を持たせる (0.7ではなく0.68など)
- witness検証で厳密な等価性チェック
- オーバーフロー防止のためビット幅管理

---

## 実装詳細

### Witness計算

Circom回路では、複雑な計算(平方根、除算)は**witness側**で事前計算し、**回路側**で検証します。

#### Witness計算手順

```javascript
// 1. ノルム計算 (JavaScript側)
const normA = Math.sqrt(vectorA.reduce((sum, v) => sum + v*v, 0));
const normB = Math.sqrt(vectorB.reduce((sum, v) => sum + v*v, 0));

// 2. 内積計算
const dotProduct = vectorA.reduce((sum, v, i) => sum + v * vectorB[i], 0);

// 3. コサイン類似度計算
const similarity = Math.round((dotProduct * SCALE) / (normA * normB));
```

#### 回路内検証

```circom
// 検証制約: similarity × normA × normB === dotProduct × SCALE
signal lhs;
signal rhs;

lhs <== similarity * normA * normB;
rhs <== dotProduct * SCALE;

lhs === rhs;  // 制約として強制
```

### ゼロ除算対策

```circom
component normACheck = GreaterThan(64);
normACheck.in[0] <== normA;
normACheck.in[1] <== 0;

component normBCheck = GreaterThan(64);
normBCheck.in[0] <== normB;
normBCheck.in[1] <== 0;

isValid <== normACheck.out * normBCheck.out;
```

---

## 使用方法

### 1. 環境セットアップ

```bash
# 依存関係インストール
npm install

# Powers of Tau セットアップ (初回のみ)
# 既に powersOfTau28_hez_final_12.ptau が存在する場合はスキップ
wget https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_12.ptau
```

### 2. 回路コンパイル

```bash
# Circom回路をコンパイル
circom circuits/csi_subcarrier_selector.circom --r1cs --wasm --sym

# または既存のコンパイルスクリプトを使用
node scripts/compile.js
```

### 3. Witnessデータ生成

```bash
# テストスクリプトでwitness生成
node scripts/test_csi_selector.js

# 生成されたファイル: csi_selector_witness.json
```

**Witness JSONフォーマット**:
```json
{
  "reference": [8500, 6200, 4800, 3100],
  "candidates": [
    [8200, 6500, 4500, 3300],
    [4500, 3000, 8500, 6000]
  ],
  "referenceNorm": 11747,
  "candidateNorms": [11831, 11489],
  "similarities": [9990, 8281]
}
```

### 4. 証明生成と検証

```bash
# セットアップ (信頼されたセットアップ)
snarkjs groth16 setup csi_subcarrier_selector.r1cs powersOfTau28_hez_final_12.ptau circuit_0000.zkey

# 証明生成
snarkjs groth16 prove circuit_0000.zkey witness.wtns proof.json public.json

# 検証
snarkjs groth16 verify verification_key.json public.json proof.json
```

### 5. スマートコントラクト生成 (オプション)

```bash
# Solidityバリデーター生成
snarkjs zkey export solidityverifier circuit_0000.zkey CSISubcarrierVerifier.sol

# ブロックチェーン上での検証が可能
```

---

## パフォーマンス最適化

### 計算量分析

| 操作 | 計算量 | 制約数 |
|------|--------|--------|
| 内積計算 | O(N) | N乗算 + (N-1)加算 |
| ノルム計算 | O(N) | N乗算 + (N-1)加算 |
| 類似度検証 | O(1) | 3乗算 + 1等価性制約 |
| M候補選択 | O(M) | M個の類似度計算 |

**N=4, M=2の場合**:
- 総制約数: 約50-60制約
- 証明生成時間: <100ms (典型的なマシン)
- 検証時間: <10ms

### リアルタイム処理のための最適化

#### 1. **並列化**
```javascript
// 複数候補の類似度を並列計算
const similarities = await Promise.all(
  candidates.map(candidate => calculateCosineSimilarity(reference, candidate))
);
```

#### 2. **インクリメンタル更新**
```javascript
// 参照ベクトルのノルムをキャッシュ
const cachedRefNorm = calculateNorm(reference);

// 候補評価時に再利用
candidates.forEach(candidate => {
  const similarity = calculateSimilarityWithCachedNorm(
    reference, candidate, cachedRefNorm
  );
});
```

#### 3. **早期打ち切り**
```javascript
// 閾値以下の候補は即座にスキップ
const viableCandidates = candidates.filter(candidate => {
  const quickEstimate = estimateSimilarity(reference, candidate);
  return quickEstimate >= THRESHOLD;
});
```

### メモリ効率化

**ベクトル次元の選択**:
- N=4: 低次元、高速計算、精度はやや低い
- N=8: バランス型、推奨
- N=16: 高精度、計算コスト増

**バッチ処理**:
```javascript
// 複数フレームをまとめて処理
const batchSize = 10;
const batchResults = processBatch(csiFrames.slice(0, batchSize));
```

---

## トラブルシューティング

### よくある問題

#### 1. **オーバーフロー**
**症状**: 大きなベクトル値で計算失敗

**解決策**:
```javascript
// 入力を正規化
const normalize = (vector) => {
  const max = Math.max(...vector.map(Math.abs));
  return vector.map(v => v / max);
};
```

#### 2. **精度不足**
**症状**: 類似度の微小な差を区別できない

**解決策**:
- スケールを10^5または10^6に増加
- ベクトル次元Nを増やす

#### 3. **検証失敗**
**症状**: `lhs === rhs` 制約が満たされない

**解決策**:
```javascript
// 丸め誤差を考慮した検証
const tolerance = 1; // ±1の誤差を許容
const diff = Math.abs(lhs - rhs);
if (diff <= tolerance) {
  // 許容範囲内
}
```

---

## まとめ

この回路により、以下を実現できます:

✅ **プライバシー保護**: 生CSIデータを公開せずに計算結果を検証
✅ **リアルタイム処理**: 固定小数点演算による高速計算
✅ **透明性**: ゼロ知識証明による選択アルゴリズムの正当性保証
✅ **柔軟性**: パラメータ(N, M, SCALE, THRESHOLD)の調整可能

### 今後の拡張

- **動的閾値調整**: 環境ノイズに応じて閾値を自動調整
- **マルチチャネル対応**: 複数周波数帯の同時処理
- **機械学習統合**: 学習済みモデルによる参照パターン最適化
- **オンチェーン検証**: スマートコントラクトでの分散検証

---

## 参考文献

1. Circom Documentation: https://docs.circom.io/
2. snarkjs Documentation: https://github.com/iden3/snarkjs
3. Cosine Similarity: https://en.wikipedia.org/wiki/Cosine_similarity
4. Zero-Knowledge Proofs: https://z.cash/technology/zksnarks/

---

**バージョン**: 1.0.0
**最終更新**: 2025-01-10
**作成者**: CSI Web Platform Team
