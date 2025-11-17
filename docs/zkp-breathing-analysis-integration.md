# ZKP回路を使用した呼吸解析統合ガイド

## 概要

このドキュメントでは、Zero-Knowledge Proof (ZKP) 回路を使用したCSI呼吸解析システムの統合実装について説明します。

## 現在の実装状況

### ✅ 実装済み

- **タスクキューシステム**: Redis + asyncio ワーカー
- **呼吸解析パイプライン**: CSIデータアップロード → タスクエンキュー → ワーカー処理
- **模擬解析**: ランダムな呼吸率・信頼度スコア生成
- **ZKP回路**: `csi_subcarrier_selector.circom` (CSIサブキャリア選択用)
- **ZKP証明スクリプト**: setup, prove, verify (Node.js)
- **ZKP APIエンドポイント**: `/api/v2/breathing-analysis/{analysis_id}/zkp`

### ❌ 未実装

- **実際のCSI信号処理**: pcapファイルからのCSI振幅データ抽出
- **ZKP回路のバックエンド統合**: Python ↔ Node.js ZKPスクリプト連携
- **自動ZKP証明生成**: 呼吸解析時の自動証明生成

## アーキテクチャ

### 現在のフロー（模擬実装）

```
┌─────────────┐
│ PCAP Upload │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│ CSIDataService      │
│ - ファイル保存      │
│ - IPFS保存         │
│ - タスクエンキュー  │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ Task Queue (Redis)  │
│ - Priority Queue    │
│ - 3 Workers         │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────────┐
│ csi_breathing_analysis  │
│ - 模擬解析 (random)     │
│ - 呼吸率: 12-25 bpm    │
│ - 信頼度: 70-99%       │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────┐
│ BreathingAnalysis   │
│ - DB保存            │
│ - IPFS保存          │
└─────────────────────┘
```

### 目標フロー（ZKP統合）

```
┌─────────────┐
│ PCAP Upload │
└──────┬──────┘
       │
       ▼
┌────────────────────────────┐
│ CSIDataService             │
│ 1. ファイル保存            │
│ 2. CSI抽出 (scapy)         │
│ 3. IPFS保存                │
│ 4. タスクエンキュー        │
└──────┬─────────────────────┘
       │
       ▼
┌─────────────────────┐
│ Task Queue (Redis)  │
└──────┬──────────────┘
       │
       ▼
┌────────────────────────────────┐
│ csi_breathing_analysis_task    │
│ 1. CSIデータ読み込み           │
│ 2. サブキャリア選択            │
│ 3. 呼吸周波数検出              │
│ 4. ZKP証明生成 ───────────┐   │
└──────┬─────────────────────┘   │
       │                         │
       ▼                         ▼
┌─────────────────────┐  ┌──────────────────────┐
│ BreathingAnalysis   │  │ ZKP Service          │
│ - DB保存            │  │ - Node.js呼び出し    │
│ - IPFS保存          │  │ - 証明生成           │
│ - ZKP証明データ保存 │  │ - 検証可能性         │
└─────────────────────┘  └──────────────────────┘
                                 │
                                 ▼
                         ┌──────────────────┐
                         │ ZKP Circuit      │
                         │ csi_subcarrier_  │
                         │ selector.circom  │
                         └──────────────────┘
```

## 実装ステップ

### Phase 1: CSI信号処理の実装

**目的**: pcapファイルから実際のCSI振幅データを抽出

**実装場所**: `backend/app/services/pcap_analyzer.py`

**主要タスク**:
```python
def extract_csi_amplitude(pcap_file_path: str) -> List[float]:
    """
    PCAPファイルからCSI振幅データを抽出

    Returns:
        CSI振幅の時系列データ（256サンプル）
    """
    # 1. scapyでCSIパケット読み込み
    # 2. CSI値をデコード
    # 3. 振幅計算: |H| = sqrt(real^2 + imag^2)
    # 4. 正規化: 0-1000の範囲に変換
    pass
```

**依存ライブラリ**:
- `scapy`: パケット解析
- `numpy`: 数値計算

### Phase 2: ZKP回路との連携実装

**目的**: PythonバックエンドからNode.js ZKPスクリプトを呼び出し

**実装場所**: `backend/app/services/zkp_service.py`

**主要タスク**:
```python
class ZKPService:
    async def generate_csi_breathing_proof(
        self,
        csi_amplitude: List[int],
        breathing_rate: float,
        breathing_frequency: float,
        confidence_score: float,
        timestamp: datetime
    ) -> Dict[str, Any]:
        """
        CSI呼吸解析のZKP証明を生成

        Args:
            csi_amplitude: CSI振幅データ（256サンプル）
            breathing_rate: 呼吸率（bpm）
            breathing_frequency: 呼吸周波数（Hz）
            confidence_score: 信頼度スコア
            timestamp: タイムスタンプ

        Returns:
            proof: ZKP証明データ
            publicSignals: 公開シグナル
            commitment: コミットメント
        """
        # 1. 入力データの準備
        input_data = {
            "csiData": csi_amplitude[:256],  # 256サンプル
            "threshold": int(confidence_score * 100),
            "timestamp": int(timestamp.timestamp())
        }

        # 2. 入力ファイル作成
        input_file = f"/tmp/zkp_input_{uuid.uuid4()}.json"
        with open(input_file, 'w') as f:
            json.dump(input_data, f)

        # 3. Node.jsスクリプト実行
        result = await asyncio.create_subprocess_exec(
            'node',
            'zkp/scripts/prove_csi_selector.js',
            input_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await result.communicate()

        # 4. 証明データ解析
        proof_data = json.loads(stdout)

        return {
            "proof": proof_data["proof"],
            "publicSignals": proof_data["publicSignals"],
            "commitment": proof_data["commitment"],
            "metadata": {
                "breathing_rate": breathing_rate,
                "breathing_frequency": breathing_frequency,
                "timestamp": timestamp.isoformat()
            }
        }
```

### Phase 3: 呼吸解析タスクの拡張

**目的**: 実際のCSI解析とZKP証明生成を統合

**実装場所**: `backend/app/services/analysis_tasks.py`

**修正内容**:
```python
async def perform_breathing_analysis(file_data: bytes, params: Dict) -> Dict[str, Any]:
    """実際のCSI呼吸解析処理"""

    # 1. CSI振幅データ抽出
    from app.services.pcap_analyzer import extract_csi_amplitude
    csi_amplitude = extract_csi_amplitude(file_data)

    # 2. 呼吸周波数検出（FFT解析）
    import numpy as np
    from scipy.fft import fft, fftfreq

    # FFT実行
    fft_result = fft(csi_amplitude)
    frequencies = fftfreq(len(csi_amplitude), d=0.1)  # 10Hz サンプリング

    # ピーク検出
    power_spectrum = np.abs(fft_result)
    breathing_freq_hz = frequencies[np.argmax(power_spectrum[1:len(power_spectrum)//2])]
    breathing_rate = breathing_freq_hz * 60  # Hz → bpm変換

    # 3. 信頼度計算
    peak_power = np.max(power_spectrum)
    noise_power = np.mean(power_spectrum)
    confidence_score = min(peak_power / noise_power / 10, 0.99)

    # 4. 呼吸パターン抽出
    breathing_pattern = csi_amplitude.tolist()

    return {
        "breathing_rate": round(breathing_rate, 1),
        "breathing_frequency": round(breathing_freq_hz, 4),
        "confidence_score": round(confidence_score, 2),
        "breathing_pattern": breathing_pattern,
        "csi_amplitude": csi_amplitude.tolist(),
        "quality_metrics": {
            "peak_power": float(peak_power),
            "noise_power": float(noise_power),
            "snr": float(peak_power / noise_power)
        }
    }
```

```python
async def csi_breathing_analysis_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """CSI呼吸解析タスク（ZKP統合版）"""

    # ... 既存のコード ...

    # 解析実行
    analysis_result = await perform_breathing_analysis(file_data, analysis_params)

    # BreathingAnalysis作成（既存）
    breathing_analysis = BreathingAnalysis(...)
    db.add(breathing_analysis)
    db.commit()
    db.refresh(breathing_analysis)

    # ✨ ZKP証明生成（新規）
    from app.services.zkp_service import ZKPService
    zkp_service = ZKPService()

    try:
        zkp_proof = await zkp_service.generate_csi_breathing_proof(
            csi_amplitude=analysis_result["csi_amplitude"],
            breathing_rate=analysis_result["breathing_rate"],
            breathing_frequency=analysis_result["breathing_frequency"],
            confidence_score=analysis_result["confidence_score"],
            timestamp=datetime.utcnow()
        )

        # ZKP証明をIPFSに保存
        zkp_ipfs_hash = await ipfs_service.upload_json(zkp_proof)

        # DB更新
        breathing_analysis.blockchain_tx_hash = zkp_proof["commitment"]
        breathing_analysis.ipfs_hash = zkp_ipfs_hash
        db.commit()

        logger.info(f"ZKP proof generated: {zkp_ipfs_hash}")

    except Exception as e:
        logger.error(f"ZKP proof generation failed: {e}")
        # ZKP失敗でも呼吸解析結果は保持

    return {
        "analysis_id": str(breathing_analysis.id),
        "breathing_rate": analysis_result["breathing_rate"],
        "confidence_score": analysis_result["confidence_score"],
        "zkp_commitment": zkp_proof.get("commitment"),
        "status": "completed"
    }
```

### Phase 4: ZKP検証エンドポイントの実装

**実装場所**: `backend/app/api/v2/zkp.py` (既存ファイル)

**実装内容**:
```python
@router.get("/breathing-analysis/{analysis_id}/zkp/verify")
async def verify_breathing_analysis_zkp(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    zkp_service: ZKPService = Depends(get_zkp_service)
):
    """
    呼吸解析結果のZKP証明を検証

    Returns:
        isValid: 証明の有効性
        publicSignals: 公開シグナル
        verificationTimestamp: 検証実行時刻
    """
    # 1. 呼吸解析結果取得
    breathing_service = BreathingAnalysisService(db)
    analysis = await breathing_service.get_analysis_result(analysis_id)

    if not analysis or not analysis.blockchain_tx_hash:
        raise HTTPException(
            status_code=404,
            detail="ZKP proof not found for this analysis"
        )

    # 2. IPFS からZKP証明取得
    zkp_proof = await ipfs_service.retrieve_json(analysis.ipfs_hash)

    # 3. ZKP検証実行
    is_valid = await zkp_service.verify_proof(
        proof=zkp_proof["proof"],
        public_signals=zkp_proof["publicSignals"]
    )

    return {
        "isValid": is_valid,
        "analysisId": analysis_id,
        "publicSignals": zkp_proof["publicSignals"],
        "commitment": zkp_proof["commitment"],
        "verificationTimestamp": datetime.utcnow().isoformat(),
        "metadata": zkp_proof["metadata"]
    }
```

## 実装ロードマップ

### Week 1: CSI信号処理
- [ ] pcapファイルからCSIデータ抽出実装
- [ ] FFT解析による呼吸周波数検出
- [ ] ユニットテスト作成

### Week 2: ZKP連携基盤
- [ ] ZKPServiceクラス拡張
- [ ] Node.jsスクリプト呼び出し機構
- [ ] 入力データ変換・正規化

### Week 3: 統合実装
- [ ] 呼吸解析タスクにZKP証明生成を統合
- [ ] エラーハンドリング強化
- [ ] ログ・モニタリング実装

### Week 4: 検証・テスト
- [ ] ZKP検証エンドポイント実装
- [ ] E2Eテスト（アップロード → 解析 → 証明 → 検証）
- [ ] パフォーマンステスト

## 技術要件

### 依存ライブラリ追加

**Python (backend/requirements.txt)**:
```
scapy>=2.5.0
scipy>=1.11.0
numpy>=1.24.0
```

**Node.js (zkp/package.json)**:
既存のsnarkjsライブラリを使用

### ZKP回路のセットアップ

```bash
cd zkp
npm install
npm run compile:selector
npm run setup
```

### 環境変数

**backend/.env**:
```
ZKP_CIRCUIT_PATH=../zkp/circuits
ZKP_PROVING_KEY_PATH=../zkp/proofs/csi_selector_proving_key.zkey
ZKP_VERIFICATION_KEY_PATH=../zkp/proofs/csi_selector_verification_key.json
```

## セキュリティ考慮事項

1. **証明の改ざん防止**: IPFS上の証明データにコンテンツハッシュ検証
2. **タイムスタンプ検証**: 証明生成時刻の妥当性チェック
3. **入力範囲検証**: CSI振幅データの範囲制約（0-1000）
4. **DoS対策**: ZKP証明生成のレート制限

## パフォーマンス最適化

1. **証明生成の非同期化**: バックグラウンドタスクで実行
2. **キャッシング**: 検証キーのメモリキャッシュ
3. **バッチ処理**: 複数の証明生成を並列実行
4. **タイムアウト設定**: ZKP生成の最大実行時間（60秒）

## トラブルシューティング

### よくある問題

**1. Node.jsスクリプトが見つからない**
```bash
# ZKPスクリプトの権限確認
chmod +x zkp/scripts/*.js
```

**2. 証明生成がタイムアウト**
```python
# タイムアウト設定を延長
result = await asyncio.wait_for(
    zkp_service.generate_proof(...),
    timeout=120  # 120秒
)
```

**3. CSI抽出エラー**
```python
# pcapファイルフォーマット確認
from scapy.all import rdpcap
packets = rdpcap(pcap_file)
print(f"Total packets: {len(packets)}")
```

## 参考資料

- [ZKP統合設計書](./zkp-integration-design.md)
- [ZKP Phase 1 実装](./zkp-phase1-implementation.md)
- [CSI Selector ZKP Guide](../zkp/CSI_SELECTOR_ZKP_GUIDE.md)
- [Quick Start Guide](../zkp/QUICK_START.md)

## 更新履歴

- 2025-11-17: 初版作成（現状分析とZKP統合フロー）
