# ZKP (Zero-Knowledge Proof) System

CSI呼吸監視システムのゼロ知識証明実装

## 📁 プロジェクト構成

```
zkp/
├── circuits/                           # Circom回路定義
│   ├── breathing_verifier.circom      # 呼吸数検証回路
│   └── csi_subcarrier_selector.circom # CSIサブキャリア選択回路 ⭐
├── scripts/                            # 証明生成・検証スクリプト
├── test/                               # テストファイル
├── build/                              # コンパイル出力
├── keys/                               # 証明鍵・検証鍵
└── proofs/                             # 生成された証明
```

## 🎯 利用可能な回路

### 1. breathing_verifier.circom - 呼吸数検証回路
- 呼吸数が正常範囲内（10-30 bpm）
- 信頼度スコアが十分に高い（70%以上）

### 2. csi_subcarrier_selector.circom - CSIサブキャリア選択回路 ⭐
- コサイン類似度計算と最適サブキャリア選択
- **証明生成・検証が成功している実用回路**

## 🚀 クイックスタート

```bash
# インストール
npm install

# CSIサブキャリア選択の証明生成・検証
node scripts/compile_csi_selector.js    # コンパイル
node scripts/setup_csi_selector.js      # セットアップ（初回のみ）
node scripts/prove_csi_selector.js      # 証明生成（約10秒）
node scripts/verify_csi_selector.js     # 証明検証（約2秒）
```

## 📚 ドキュメント

- **クイックスタート**: `QUICK_START.md`
- **詳細ガイド**: `CSI_SELECTOR_ZKP_GUIDE.md`

## ⚠️ 重要な制約

ノルムが整数になるベクトル（ピタゴラス数）を使用してください:
- ✅ `[3, 4, 0, 0]` (ノルム = 5)
- ✅ `[5, 12, 0, 0]` (ノルム = 13)
- ❌ `[1, 2, 3, 4]` (ノルム = 5.477... 非整数)
