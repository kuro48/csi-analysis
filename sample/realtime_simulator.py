#!/usr/bin/env python3
"""
リアルタイムCSI解析シミュレータ
デバイス認証なしでリアルタイム解析機能をテスト
"""

import asyncio
import sys
import os
import json
import numpy as np
from datetime import datetime
import aiohttp
import time
import struct

# バックエンドのリアルタイム解析器を直接インポート
sys.path.append('/Users/ryunosukekurokawa/Documents/class/lab/M1/研究関連/csi-web-platform/backend')

try:
    from app.services.realtime_csi_analyzer import realtime_analyzer
    from app.services.websocket import realtime_service, manager
    BACKEND_AVAILABLE = True
except ImportError as e:
    print(f"バックエンドモジュールのインポートに失敗: {e}")
    BACKEND_AVAILABLE = False

class CSIDataSimulator:
    """CSIデータシミュレータ"""

    def __init__(self):
        self.device_id = "ESP32_SIMULATOR_001"
        self.is_running = False

    def load_sample_data(self, filename):
        """サンプルCSIデータを読み込み"""
        try:
            with open(filename, 'rb') as f:
                # ヘッダー読み込み
                num_samples = struct.unpack('I', f.read(4))[0]
                num_subcarriers = struct.unpack('I', f.read(4))[0]
                sampling_rate = struct.unpack('I', f.read(4))[0]

                print(f"データ読み込み: {num_samples}サンプル, {num_subcarriers}サブキャリア, {sampling_rate}Hz")

                # CSIデータ読み込み
                csi_data = []
                for sample in range(num_samples):
                    sample_data = []
                    for sc in range(num_subcarriers):
                        real = struct.unpack('f', f.read(4))[0]
                        imag = struct.unpack('f', f.read(4))[0]
                        sample_data.append(complex(real, imag))
                    csi_data.append(sample_data)

                return np.array(csi_data), sampling_rate

        except Exception as e:
            print(f"サンプルデータ読み込みエラー: {e}")
            return None, None

    def convert_to_bytes(self, csi_matrix):
        """CSI行列をバイト列に変換"""
        try:
            # シンプルなバイナリ形式に変換
            data = []
            for sample in csi_matrix:
                for val in sample:
                    data.extend(struct.pack('f', val.real))
                    data.extend(struct.pack('f', val.imag))
            return bytes(data)
        except Exception as e:
            print(f"バイト変換エラー: {e}")
            return b''

    async def simulate_realtime_analysis(self, csi_data, sampling_rate=100):
        """リアルタイム解析をシミュレート"""
        if not BACKEND_AVAILABLE:
            print("バックエンドが利用できないため、模擬解析を実行")
            return await self.mock_analysis()

        print(f"リアルタイム解析開始 - {len(csi_data)}サンプル")

        # データをチャンクに分割してリアルタイム送信をシミュレート
        chunk_size = sampling_rate  # 1秒分のデータ
        results = []

        for i in range(0, len(csi_data), chunk_size):
            chunk = csi_data[i:i+chunk_size]
            chunk_bytes = self.convert_to_bytes(chunk)

            if len(chunk_bytes) > 0:
                try:
                    # リアルタイム解析実行
                    result = await realtime_analyzer.analyze_csi_data(self.device_id, chunk_bytes)

                    if result:
                        analysis_data = {
                            "timestamp": result.timestamp.isoformat(),
                            "breathing_rate": result.breathing_data.breathing_rate,
                            "breathing_amplitude": result.breathing_data.amplitude,
                            "breathing_confidence": result.breathing_data.confidence,
                            "signal_quality": result.signal_quality,
                            "motion_detected": result.motion_detected,
                            "anomaly_score": result.anomaly_score,
                            "raw_signal": result.breathing_data.raw_signal
                        }

                        results.append(analysis_data)
                        print(f"チャンク {i//chunk_size + 1}: 呼吸数 {result.breathing_data.breathing_rate:.1f}回/分, 信頼度 {result.breathing_data.confidence:.3f}")

                        # WebSocketブロードキャストをシミュレート（実際のサービスが利用可能な場合）
                        try:
                            await realtime_service.broadcast_csi_analysis(self.device_id, analysis_data)
                        except Exception as ws_error:
                            print(f"WebSocket配信エラー: {ws_error}")

                except Exception as e:
                    print(f"解析エラー (チャンク {i//chunk_size + 1}): {e}")

            # リアルタイム処理をシミュレート
            await asyncio.sleep(0.5)  # 実際より高速化

        return results

    async def mock_analysis(self):
        """模擬解析（バックエンドが利用できない場合）"""
        results = []
        breathing_rates = [15.2, 16.1, 15.8, 16.5, 15.9, 16.3, 15.7, 16.0]

        for i, rate in enumerate(breathing_rates):
            analysis_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "breathing_rate": rate,
                "breathing_amplitude": 0.7 + np.random.normal(0, 0.1),
                "breathing_confidence": 0.85 + np.random.normal(0, 0.05),
                "signal_quality": 0.9 + np.random.normal(0, 0.05),
                "motion_detected": np.random.random() < 0.1,
                "anomaly_score": np.random.random() * 0.2,
                "raw_signal": np.random.normal(0, 0.1, 20).tolist()
            }

            results.append(analysis_data)
            print(f"模擬解析 {i+1}: 呼吸数 {rate:.1f}回/分")
            await asyncio.sleep(1)

        return results

async def main():
    """メイン処理"""
    print("=== リアルタイムCSI解析シミュレータ ===")

    simulator = CSIDataSimulator()

    # サンプルデータファイル
    sample_files = [
        "/Users/ryunosukekurokawa/Documents/class/lab/M1/研究関連/csi-web-platform/sample/sample_csi_normal_breathing.bin",
        "/Users/ryunosukekurokawa/Documents/class/lab/M1/研究関連/csi-web-platform/sample/sample_csi_slow_breathing.bin",
        "/Users/ryunosukekurokawa/Documents/class/lab/M1/研究関連/csi-web-platform/sample/sample_csi_fast_breathing.bin"
    ]

    for i, sample_file in enumerate(sample_files):
        if not os.path.exists(sample_file):
            print(f"サンプルファイルが見つかりません: {sample_file}")
            continue

        print(f"\n--- テスト {i+1}: {os.path.basename(sample_file)} ---")

        # サンプルデータ読み込み
        csi_data, sampling_rate = simulator.load_sample_data(sample_file)

        if csi_data is not None:
            # リアルタイム解析実行
            results = await simulator.simulate_realtime_analysis(csi_data, sampling_rate)

            # 結果サマリー
            if results:
                breathing_rates = [r['breathing_rate'] for r in results]
                avg_rate = np.mean(breathing_rates)
                avg_confidence = np.mean([r['breathing_confidence'] for r in results])

                print(f"\n解析結果サマリー:")
                print(f"  平均呼吸数: {avg_rate:.1f} 回/分")
                print(f"  平均信頼度: {avg_confidence:.3f}")
                print(f"  解析回数: {len(results)}")

        print("-" * 50)

    print("\nシミュレーション完了!")

if __name__ == "__main__":
    asyncio.run(main())