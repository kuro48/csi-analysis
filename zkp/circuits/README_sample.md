# サンプル呼吸数検証回路（学習用）

## 📚 概要

`sample_breathing.circom` は、ゼロ知識証明（ZKP）の基本概念を学ぶための超シンプルな回路です。

**目的**: 呼吸数が正常範囲（10-30 bpm）にあることを、実際の値を明かさずに証明する

## 🎯 ZKPの基本概念

### 通常の証明（ZKPなし）
```
私: 「呼吸数は15 bpmで、正常範囲内です」
相手: 「本当に15 bpmなの？確認させて」
私: 「はい、15です」
→ 実際の値（15）が相手に知られる
```

### ゼロ知識証明（ZKP）
```
私: 「呼吸数は正常範囲内です（証明を提示）」
相手: 「証明を検証...OK、確かに範囲内だ！」
→ 実際の値は知られないまま、範囲内であることだけ証明
```

## 🔧 回路の構造

```
入力: breathingRate（秘密）
  ↓
検証1: breathingRate >= 10 ?  ──┐
検証2: breathingRate <= 30 ?  ──┤
                                 ↓
                        両方とも TRUE ?
                                 ↓
                    出力: isValid (1 or 0)
```

## 📊 技術仕様

- **制約数**: 27（非常に軽量！）
- **公開入力**: 0（完全に秘密）
- **秘密入力**: 1（breathingRate）
- **出力**: 1（isValid）

## 🚀 使い方

### 1. コンパイル

```bash
circom circuits/sample_breathing.circom --r1cs --wasm --sym -o build
```

### 2. テスト実行

```bash
node scripts/test_sample.js
```

### 3. 手動テスト

```bash
# 入力データ作成
echo '{"breathingRate": 15}' > build/sample_input.json

# Witness計算
npx snarkjs wtns calculate \
  build/sample_breathing_js/sample_breathing.wasm \
  build/sample_input.json \
  build/sample_witness.wtns
```

## 📖 コード解説

### 1. テンプレート定義
```circom
template SampleBreathing() {
    signal input breathingRate;  // 秘密入力
    signal output isValid;       // 公開出力
```

### 2. 範囲チェック（下限）
```circom
component minCheck = GreaterEqThan(8);
minCheck.in[0] <== breathingRate;
minCheck.in[1] <== 10;  // 最小閾値
```

### 3. 範囲チェック（上限）
```circom
component maxCheck = LessEqThan(8);
maxCheck.in[0] <== breathingRate;
maxCheck.in[1] <== 30;  // 最大閾値
```

### 4. 結果統合（AND演算）
```circom
isValid <== minCheck.out * maxCheck.out;
// 両方が1の場合のみ、isValid = 1
```

## 🧪 テスト結果例

```
🧪 Testing breathing rate: 15 bpm
   ✅ Witness calculated
   ✅ Result: VALID ✓

🧪 Testing breathing rate: 35 bpm
   ❌ Result: INVALID ✗ (out of range)
```

## 💡 学習ポイント

1. **秘密性**: breathingRateは外部に公開されない
2. **検証可能性**: isValidを見れば範囲内かどうか分かる
3. **制約システム**: 比較演算を制約として表現
4. **論理演算**: AND演算を乗算で実現

## 🔄 発展課題

このサンプルを理解したら、以下に挑戦してみましょう：

1. 範囲を変更してみる（例: 15-25 bpm）
2. 3つの範囲チェックを追加してみる
3. 複数の入力を受け取る回路に拡張
4. 実際の証明生成・検証まで実装

## 📚 関連ファイル

- **回路**: `circuits/sample_breathing.circom`
- **テスト**: `scripts/test_sample.js`
- **コンパイル済み**: `build/sample_breathing_js/sample_breathing.wasm`

## 🌟 次のステップ

より複雑な回路を学びたい場合は、`breathing_verifier.circom` を参照してください。
こちらでは以下の機能が追加されています：

- 複数の公開入力
- より複雑な検証ロジック
- 信頼度スコアの統合

---

**Happy Learning! 🎓**
