# CSI呼吸監視システム - ゼロ知識証明統合設計書

## エグゼクティブサマリー

CSI（Channel State Information）から呼吸数を抽出する計算過程をゼロ知識証明（ZKP）回路に組み込み、プライバシーを保護しながら正しい処理が行われたことを検証可能にする。

### 目的
1. **プライバシー保護**: 生のCSIデータを公開せずに呼吸数の正当性を証明
2. **計算正当性の保証**: 信頼できる呼吸数抽出計算の実行を検証
3. **ブロックチェーン連携**: イーサリアムネットワーク上での検証可能性

### 技術選定
- **ZKPフレームワーク**: circom + snarkjs (Ethereum互換、成熟度高)
- **証明システム**: Groth16 (検証コスト最小)
- **統合方式**: ハイブリッド（オフチェーン計算 + オンチェーン検証）

---

## 1. CSI→呼吸数抽出アルゴリズムの分析

### 1.1 現在の実装 (Python)

**処理フロー**:
```
CSI生データ(bytes)
  ↓ パース
CSI行列 (N × 64 float32)
  ↓ 振幅抽出
振幅時系列 A[t] (N samples)
  ↓ ハイパスフィルタ
フィルタ済み信号 F[t]
  ↓ FFT
パワースペクトラム P[f]
  ↓ ピーク検出 (0.1~0.5Hz)
呼吸周波数 f_b [Hz]
  ↓ 変換
呼吸数 R = f_b × 60 [回/分]
```

### 1.2 数学的モデル

#### 振幅時系列抽出
```
A[t] = mean(|CSI[t, :]|) for t = 0 to N-1
where CSI[t, k] = CSI行列の時刻tサブキャリアk
```

#### ハイパスフィルタ (移動平均による低周波除去)
```
F[t] = A[t] - MA[t]
where MA[t] = (1/w) Σ(i=t-w/2 to t+w/2) A[i]
w = window_size = max(3, N/10)
```

#### FFT (離散フーリエ変換)
```
X[k] = Σ(n=0 to N-1) F[n] * e^(-2πikn/N)
P[k] = |X[k]|^2  (パワースペクトラム)
f[k] = k / N  (正規化周波数)
```

#### 呼吸ピーク検出
```
f_b = argmax(P[k]) for k where 0.1 ≤ f[k] ≤ 0.5
R = f_b × 60  (呼吸数 [回/分])
```

#### 信頼度計算
```
confidence = peak_power / average_power
where peak_power = max(P[k])
      average_power = sum(P[k]) / len(P[k])
```

---

## 2. ZKP回路設計

### 2.1 設計原則

**課題**:
- FFTは計算量が高い (O(N log N))
- 浮動小数点演算は回路で実装困難
- 回路サイズの制約 (Groth16の制約数制限)

**解決策**: ハイブリッドアプローチ
1. **オフチェーン**: 完全な処理実行（Python）
2. **ZKP回路**: 重要な計算ステップの検証
3. **コミットメント**: ハッシュによる入力データの固定

### 2.2 回路アーキテクチャ

#### アプローチ1: 完全検証回路 (フル実装)

**利点**: 完全な計算過程を検証
**欠点**: 回路サイズが巨大、証明生成時間が長い

```circom
template BreathingRateCircuit(N) {
    // Public inputs
    signal input csi_data_hash;      // CSIデータのハッシュ
    signal input breathing_rate_out; // 出力呼吸数

    // Private inputs
    signal input csi_data[N][64];    // CSI行列 (private)
    signal input amplitude_series[N]; // 振幅時系列 (intermediate)

    // 1. CSIデータのハッシュ検証
    component hasher = Poseidon(N*64);
    for (var i = 0; i < N*64; i++) {
        hasher.inputs[i] <== csi_data[i / 64][i % 64];
    }
    hasher.out === csi_data_hash;

    // 2. 振幅時系列抽出の検証
    component amplitude_extractor = AmplitudeExtractor(N, 64);
    amplitude_extractor.csi <== csi_data;
    amplitude_extractor.amplitude <== amplitude_series;

    // 3. ハイパスフィルタの検証
    component highpass = HighpassFilter(N);
    highpass.signal_in <== amplitude_series;

    // 4. FFT の検証 (簡略化)
    component fft = SimplifiedFFT(N);
    fft.signal_in <== highpass.signal_out;

    // 5. ピーク検出の検証
    component peak_detector = BreathingPeakDetector();
    peak_detector.power_spectrum <== fft.power_spectrum;
    peak_detector.breathing_rate <== breathing_rate_out;
}
```

**実装の複雑さ**: 非常に高い（FFT回路の実装が困難）

---

#### アプローチ2: 簡略検証回路 (推奨)

**利点**: 回路サイズが小さく実用的
**欠点**: 完全な計算検証ではない

```circom
template BreathingRateVerificationCircuit(N) {
    // Public inputs
    signal input csi_data_commitment;  // CSIデータのコミットメント
    signal input breathing_rate;       // 呼吸数 [回/分]
    signal input confidence;           // 信頼度 [0-100]
    signal input timestamp;            // タイムスタンプ

    // Private inputs (witness)
    signal input csi_amplitude[N];     // CSI振幅時系列
    signal input peak_frequency;       // 検出されたピーク周波数
    signal input peak_power;           // ピークパワー
    signal input total_power;          // 総パワー

    // 1. コミットメント検証
    component commitment = Poseidon(N + 1);
    for (var i = 0; i < N; i++) {
        commitment.inputs[i] <== csi_amplitude[i];
    }
    commitment.inputs[N] <== timestamp;
    commitment.out === csi_data_commitment;

    // 2. 呼吸数の範囲検証 (6~40 回/分)
    component range_check = RangeCheck(6, 40);
    range_check.value <== breathing_rate;

    // 3. 周波数と呼吸数の整合性検証
    // breathing_rate = peak_frequency * 60
    signal computed_rate <== peak_frequency * 60;
    computed_rate === breathing_rate;

    // 4. ピーク周波数の範囲検証 (0.1~0.667 Hz)
    component freq_range = RangeCheckFloat(10, 66); // 0.1*100 ~ 0.667*100
    freq_range.value <== peak_frequency * 100;

    // 5. 信頼度計算の検証
    // confidence = peak_power / (total_power / N)
    signal avg_power <== total_power / N;
    signal computed_confidence <== (peak_power * 100) / avg_power;

    // 信頼度の範囲チェック (0~100)
    component confidence_range = RangeCheck(0, 100);
    confidence_range.value <== computed_confidence;
    computed_confidence === confidence;

    // 6. CSI振幅の妥当性検証 (各値が正の範囲内)
    for (var i = 0; i < N; i++) {
        component amplitude_check = RangeCheck(0, 10000);
        amplitude_check.value <== csi_amplitude[i];
    }
}
```

**実装の複雑さ**: 中程度（実用的なバランス）

---

#### アプローチ3: ハッシュベース検証回路 (最小実装)

**利点**: 回路サイズ最小、証明生成が高速
**欠点**: 計算検証が弱い

```circom
template BreathingRateHashCircuit() {
    // Public inputs
    signal input analysis_result_hash;  // 解析結果全体のハッシュ

    // Private inputs
    signal input breathing_rate;
    signal input confidence;
    signal input timestamp;
    signal input device_id;
    signal input csi_data_hash;

    // ハッシュ検証のみ
    component hasher = Poseidon(5);
    hasher.inputs[0] <== breathing_rate;
    hasher.inputs[1] <== confidence;
    hasher.inputs[2] <== timestamp;
    hasher.inputs[3] <== device_id;
    hasher.inputs[4] <== csi_data_hash;

    hasher.out === analysis_result_hash;

    // 基本的な範囲チェックのみ
    component breathing_range = RangeCheck(6, 40);
    breathing_range.value <== breathing_rate;
}
```

**実装の複雑さ**: 低（最小限の検証）

---

### 2.3 推奨実装: アプローチ2 (簡略検証回路)

**選択理由**:
1. 実用的な回路サイズ（制約数: ~10,000）
2. 重要な計算ステップを検証
3. プライバシー保護を実現
4. 証明生成時間が実用的（< 10秒）

**検証項目**:
- ✅ CSIデータのコミットメント検証
- ✅ 呼吸数の範囲検証（生理学的妥当性）
- ✅ 周波数と呼吸数の整合性
- ✅ 信頼度計算の正当性
- ✅ 振幅データの妥当性

**検証しない項目**:
- ❌ FFT計算の完全検証（計算量が高すぎる）
- ❌ フィルタリング処理の詳細（信頼できるオフチェーン実装）

---

## 3. システムアーキテクチャ

### 3.1 全体構成

```
┌─────────────────┐
│  Edge Device    │
│  (CSI Capture)  │
└────────┬────────┘
         │ CSI Data
         ↓
┌─────────────────────────────────────────┐
│  Backend Server (FastAPI)               │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Breathing Analysis Service      │  │
│  │  (Python + NumPy)                │  │
│  │  - FFT, Filter, Peak Detection   │  │
│  └──────────┬───────────────────────┘  │
│             │                           │
│             ↓                           │
│  ┌──────────────────────────────────┐  │
│  │  ZKP Proof Generator             │  │
│  │  (snarkjs + Node.js)             │  │
│  │  - Witness Generation            │  │
│  │  - Proof Generation (Groth16)    │  │
│  └──────────┬───────────────────────┘  │
│             │                           │
└─────────────┼───────────────────────────┘
              │ Proof + Public Inputs
              ↓
┌─────────────────────────────────────────┐
│  Ethereum Network (Ganache/Mainnet)     │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Verifier Smart Contract         │  │
│  │  (Solidity)                      │  │
│  │  - Proof Verification            │  │
│  │  - Result Recording              │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### 3.2 データフロー

1. **CSIデータ取得**: エッジデバイス → バックエンド
2. **呼吸解析**: Python (realtime_csi_analyzer.py)
   - 振幅抽出
   - フィルタリング
   - FFT
   - ピーク検出
   - 呼吸数計算
3. **Witness生成**: 解析結果 → ZKP witness
4. **Proof生成**: snarkjs (5~10秒)
5. **オンチェーン検証**: スマートコントラクト
6. **結果保存**: ブロックチェーン + PostgreSQL

### 3.3 コンポーネント設計

#### 3.3.1 ZKP Proof Generator Service (新規)

**場所**: `backend/app/services/zkp_prover.py`

```python
class ZKPProverService:
    def __init__(self):
        self.circuit_path = "zkp/circuits/breathing_rate_verification.circom"
        self.proving_key_path = "zkp/keys/proving_key.zkey"

    async def generate_proof(
        self,
        breathing_data: BreathingData,
        csi_amplitude: np.ndarray
    ) -> Dict[str, Any]:
        """ZKP証明を生成"""

        # 1. Witness データ生成
        witness = self._generate_witness(breathing_data, csi_amplitude)

        # 2. snarkjs でProof生成 (Node.jsプロセス起動)
        proof = await self._call_snarkjs_prove(witness)

        # 3. Public inputsを抽出
        public_signals = self._extract_public_signals(proof)

        return {
            "proof": proof,
            "public_signals": public_signals,
            "breathing_rate": breathing_data.breathing_rate,
            "confidence": breathing_data.confidence
        }

    def _generate_witness(
        self,
        breathing_data: BreathingData,
        csi_amplitude: np.ndarray
    ) -> Dict:
        """Witness生成"""

        # コミットメント計算 (Poseidon hash)
        commitment = self._compute_commitment(
            csi_amplitude,
            breathing_data.timestamp
        )

        return {
            "csi_data_commitment": str(commitment),
            "breathing_rate": int(breathing_data.breathing_rate),
            "confidence": int(breathing_data.confidence * 100),
            "timestamp": int(breathing_data.timestamp.timestamp()),
            "csi_amplitude": csi_amplitude.tolist(),
            "peak_frequency": breathing_data.breathing_rate / 60.0,
            # ... 他のprivate inputs
        }
```

#### 3.3.2 Verifier Smart Contract (新規)

**場所**: `backend/contracts/BreathingRateVerifier.sol`

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./Verifier.sol";  // snarkjs生成の検証コントラクト

contract BreathingRateVerifier is Verifier {
    struct AnalysisRecord {
        uint256 timestamp;
        address deviceOwner;
        bytes32 csiDataCommitment;
        uint16 breathingRate;
        uint8 confidence;
        bool verified;
    }

    mapping(bytes32 => AnalysisRecord) public records;

    event BreathingRateVerified(
        bytes32 indexed recordId,
        address indexed deviceOwner,
        uint16 breathingRate,
        uint8 confidence,
        uint256 timestamp
    );

    function verifyAndRecordBreathingRate(
        uint[2] memory a,
        uint[2][2] memory b,
        uint[2] memory c,
        uint[5] memory publicInputs  // [commitment, rate, confidence, timestamp, deviceId]
    ) public returns (bytes32) {
        // ZKP検証
        require(
            verifyProof(a, b, c, publicInputs),
            "Invalid ZK proof"
        );

        // レコードID生成
        bytes32 recordId = keccak256(
            abi.encodePacked(
                publicInputs[0],  // commitment
                publicInputs[3]   // timestamp
            )
        );

        // 重複チェック
        require(!records[recordId].verified, "Already verified");

        // レコード保存
        records[recordId] = AnalysisRecord({
            timestamp: publicInputs[3],
            deviceOwner: msg.sender,
            csiDataCommitment: bytes32(publicInputs[0]),
            breathingRate: uint16(publicInputs[1]),
            confidence: uint8(publicInputs[2]),
            verified: true
        });

        emit BreathingRateVerified(
            recordId,
            msg.sender,
            uint16(publicInputs[1]),
            uint8(publicInputs[2]),
            publicInputs[3]
        );

        return recordId;
    }

    function getRecord(bytes32 recordId) public view returns (AnalysisRecord memory) {
        require(records[recordId].verified, "Record not found");
        return records[recordId];
    }
}
```

---

## 4. 実装ロードマップ

### Phase 1: 基礎実装 (4-6週間)

#### Week 1-2: 環境構築
- [ ] circom + snarkjs セットアップ
- [ ] 開発環境整備（Node.js, Rust toolchain）
- [ ] サンプル回路のテスト

#### Week 3-4: 回路開発
- [ ] BreathingRateVerificationCircuit実装
- [ ] RangeCheck, Poseidon ヘルパー回路実装
- [ ] 回路のコンパイルとテスト

#### Week 5-6: バックエンド統合
- [ ] ZKPProverService実装
- [ ] Witness生成ロジック実装
- [ ] 既存の解析サービスとの統合

### Phase 2: スマートコントラクト実装 (2-3週間)

#### Week 7-8: コントラクト開発
- [ ] BreathingRateVerifier.sol実装
- [ ] Trustedセットアップ（Powers of Tau）
- [ ] Verifier.solの自動生成とデプロイ

#### Week 9: テストとデバッグ
- [ ] Ganacheでの統合テスト
- [ ] ガスコスト最適化
- [ ] セキュリティ監査

### Phase 3: フロントエンド統合 (2週間)

#### Week 10-11: UI実装
- [ ] ZKP証明生成ステータス表示
- [ ] ブロックチェーン検証結果の表示
- [ ] トランザクション履歴UI

### Phase 4: 本番デプロイ準備 (2週間)

#### Week 12-13: 最適化
- [ ] 証明生成の並列化
- [ ] キャッシュ戦略の実装
- [ ] パフォーマンステスト

#### Week 14: 本番リリース
- [ ] Ethereum Mainnet / L2 デプロイ
- [ ] ドキュメント整備
- [ ] モニタリング設定

---

## 5. 技術的考慮事項

### 5.1 パフォーマンス

| 指標 | 目標値 | 備考 |
|-----|-------|------|
| 証明生成時間 | < 10秒 | 並列化で短縮可能 |
| 検証時間 (オンチェーン) | < 1秒 | Groth16の利点 |
| ガスコスト | < 500,000 gas | ~$10-20 @ 50 Gwei |
| 回路制約数 | < 10,000 | 実用的なサイズ |

### 5.2 セキュリティ

**脅威モデル**:
1. **悪意ある証明者**: 不正な呼吸数を証明しようとする
   - 対策: 範囲チェック、整合性検証
2. **データ改ざん**: CSIデータの事後改変
   - 対策: コミットメントスキーム
3. **リプレイ攻撃**: 同じ証明の再利用
   - 対策: タイムスタンプ + ナンス

**監査項目**:
- [ ] 回路のフォーマル検証
- [ ] スマートコントラクトの監査
- [ ] Trusted Setupの透明性

### 5.3 プライバシー

**保護される情報**:
- ✅ 生のCSI波形データ
- ✅ 振幅時系列の詳細
- ✅ FFT計算の中間結果

**公開される情報**:
- 📊 呼吸数（範囲内であることのみ検証）
- 📊 信頼度（0~100）
- 📊 タイムスタンプ
- 📊 コミットメント（ハッシュ値のみ）

### 5.4 拡張性

**将来の拡張**:
1. **マルチデバイス対応**: 複数デバイスの証明をバッチ処理
2. **証明集約**: Recursive SNARKsによる複数証明の統合
3. **L2展開**: Optimistic RollupやzkRollupへの移行
4. **高度な解析**: 心拍変動、睡眠段階の検証

---

## 6. 依存関係とツール

### 6.1 ZKPツールチェーン

```json
{
  "circom": "^2.1.0",
  "snarkjs": "^0.7.0",
  "ffjavascript": "^0.2.0"
}
```

### 6.2 スマートコントラクト開発

```json
{
  "hardhat": "^2.19.0",
  "@openzeppelin/contracts": "^5.0.0",
  "ethers": "^6.9.0"
}
```

### 6.3 バックエンド追加依存

```
# requirements.txt に追加
py_ecc>=6.0.0        # 楕円曲線暗号
poseidon-hash>=0.1.0 # Poseidon hash
```

---

## 7. まとめ

### 採用するアプローチ
✅ **簡略検証回路（アプローチ2）+ Groth16**

### 主要な利点
1. **プライバシー保護**: CSIデータを公開せずに検証
2. **実用的なパフォーマンス**: 10秒以内の証明生成
3. **Ethereum互換**: 既存のインフラ活用
4. **段階的実装**: Phase 1から順次展開可能

### 次のステップ
1. circom環境のセットアップ
2. PoC回路の実装
3. バックエンドサービスの統合開始

---

**作成日**: 2025年10月28日
**バージョン**: 1.0
**ステータス**: 設計完了、実装準備中
