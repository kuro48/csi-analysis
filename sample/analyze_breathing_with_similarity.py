#!/usr/bin/env python3
"""
PCAPファイルからCSIデータを抽出し、コサイン類似度と呼吸数を計算するスクリプト
"""

import sys
import os
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

# バックエンドのパスを追加
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.pcap_analyzer import PCAPAnalyzer


def calculate_cosine_similarity(vector1: np.ndarray, vector2: np.ndarray) -> float:
    """
    2つのベクトル間のコサイン類似度を計算

    Args:
        vector1: ベースベクトル
        vector2: 比較ベクトル

    Returns:
        コサイン類似度 (0.0 ~ 1.0)
    """
    # ゼロベクトルチェック
    norm1 = np.linalg.norm(vector1)
    norm2 = np.linalg.norm(vector2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    # コサイン類似度 = 内積 / (ノルム1 * ノルム2)
    similarity = np.dot(vector1, vector2) / (norm1 * norm2)

    return float(similarity)


def extract_csi_from_pcap(pcap_file: Path) -> Tuple[np.ndarray, List[float]]:
    """
    PCAPファイルからCSI振幅データを抽出

    Args:
        pcap_file: PCAPファイルのパス

    Returns:
        (csi_amplitudes, timestamps) のタプル
        csi_amplitudes: shape (num_packets, num_subcarriers)
        timestamps: パケットのタイムスタンプリスト
    """
    print(f"\n📂 PCAPファイル解析: {pcap_file.name}")

    analyzer = PCAPAnalyzer()
    result = analyzer.analyze_pcap_file(str(pcap_file))

    # time_seriesデータ取得
    time_series = result.get('time_series', {})
    amplitudes_data = time_series.get('amplitudes', [])
    timestamps = time_series.get('timestamps', [])

    if not amplitudes_data or not timestamps:
        # 代替: csi_packetsから直接抽出
        csi_packets = result.get('csi_packets', [])
        if not csi_packets:
            raise ValueError(f"CSIデータが見つかりませんでした: {pcap_file}")

        print(f"   ℹ️  csi_packetsから直接データを抽出します")
        amplitudes_data = []
        timestamps = []

        for packet in csi_packets:
            amplitudes_data.append(packet.get('amplitudes', []))
            timestamps.append(packet.get('timestamp', 0.0))

    # numpy配列に変換
    csi_amplitudes = np.array(amplitudes_data)

    print(f"   ✓ {len(timestamps)} データポイント抽出")
    print(f"   ✓ CSI振幅データ形状: {csi_amplitudes.shape}")

    return csi_amplitudes, timestamps


def calculate_breathing_rate(csi_amplitudes: np.ndarray, timestamps: List[float]) -> Dict:
    """
    CSI振幅データから呼吸数を推定

    Args:
        csi_amplitudes: CSI振幅データ (num_packets, num_subcarriers)
        timestamps: タイムスタンプリスト

    Returns:
        呼吸解析結果の辞書
    """
    print("\n🫁 呼吸数推定中...")

    # サブキャリアの平均振幅を計算（時系列データ）
    mean_amplitude = np.mean(csi_amplitudes, axis=1)

    # サンプリングレート計算
    if len(timestamps) > 1:
        time_diffs = np.diff(timestamps)
        sampling_rate = 1.0 / np.mean(time_diffs) if np.mean(time_diffs) > 0 else 100.0
    else:
        sampling_rate = 100.0  # デフォルト

    print(f"   ✓ サンプリングレート: {sampling_rate:.2f} Hz")
    print(f"   ✓ データポイント数: {len(mean_amplitude)}")

    # FFTで周波数解析
    n = len(mean_amplitude)
    fft_result = np.fft.fft(mean_amplitude)
    freqs = np.fft.fftfreq(n, 1/sampling_rate)

    # 正の周波数のみ取得
    positive_freqs = freqs[:n//2]
    power_spectrum = np.abs(fft_result[:n//2]) ** 2

    # 呼吸の周波数範囲（0.1-0.5 Hz = 6-30 回/分）
    breathing_freq_min = 0.1  # Hz (6 回/分)
    breathing_freq_max = 0.5  # Hz (30 回/分)

    # 該当範囲のインデックス
    valid_indices = np.where(
        (positive_freqs >= breathing_freq_min) &
        (positive_freqs <= breathing_freq_max)
    )[0]

    if len(valid_indices) == 0:
        print("   ⚠️  呼吸周波数範囲にピークが見つかりません")
        return {
            "breathing_rate": None,
            "confidence": 0.0,
            "dominant_frequency": None
        }

    # 最大パワーの周波数を取得
    valid_power = power_spectrum[valid_indices]
    valid_frequencies = positive_freqs[valid_indices]

    max_power_idx = np.argmax(valid_power)
    dominant_frequency = valid_frequencies[max_power_idx]
    breathing_rate = dominant_frequency * 60  # Hzから回/分に変換

    # 信頼度計算（ピークの明確さ）
    mean_power = np.mean(valid_power)
    max_power = valid_power[max_power_idx]
    confidence = min(max_power / (mean_power + 1e-10), 1.0)

    print(f"   ✓ 推定呼吸数: {breathing_rate:.1f} 回/分")
    print(f"   ✓ 支配周波数: {dominant_frequency:.3f} Hz")
    print(f"   ✓ 信頼度: {confidence:.2%}")

    return {
        "breathing_rate": float(breathing_rate),
        "confidence": float(confidence),
        "dominant_frequency": float(dominant_frequency),
        "sampling_rate": float(sampling_rate),
        "total_samples": len(mean_amplitude)
    }


def main():
    """メイン処理"""
    print("=" * 70)
    print("🔬 CSI呼吸解析 & コサイン類似度計算")
    print("=" * 70)

    # PCAPファイルのパス
    base_dir = Path(__file__).parent / "data"
    base_pcap = base_dir / "test1219-noperson.pcap"
    person_pcap = base_dir / "test1219-person.pcap"

    # ファイル存在確認
    if not base_pcap.exists():
        print(f"❌ ベースファイルが見つかりません: {base_pcap}")
        return 1

    if not person_pcap.exists():
        print(f"❌ 人物ファイルが見つかりません: {person_pcap}")
        return 1

    try:
        # 1. ベースデータ（人なし）の抽出
        print("\n" + "=" * 70)
        print("📊 STEP 1: ベースデータ（人なし）の抽出")
        print("=" * 70)
        base_amplitudes, base_timestamps = extract_csi_from_pcap(base_pcap)

        # 2. 人物データの抽出
        print("\n" + "=" * 70)
        print("📊 STEP 2: 人物データの抽出")
        print("=" * 70)
        person_amplitudes, person_timestamps = extract_csi_from_pcap(person_pcap)

        # 3. コサイン類似度計算
        print("\n" + "=" * 70)
        print("📐 STEP 3: コサイン類似度計算")
        print("=" * 70)

        # データ数を揃える
        min_samples = min(len(base_amplitudes), len(person_amplitudes))
        base_vector = base_amplitudes[:min_samples].flatten()
        person_vector = person_amplitudes[:min_samples].flatten()

        similarity = calculate_cosine_similarity(base_vector, person_vector)

        print(f"\n   📏 ベクトル次元: {len(base_vector):,}")
        print(f"   🎯 コサイン類似度: {similarity:.6f}")
        print(f"   📊 類似度パーセンテージ: {similarity * 100:.2f}%")

        # 4. 呼吸数推定（人物データ）
        print("\n" + "=" * 70)
        print("🫁 STEP 4: 呼吸数推定（人物データ）")
        print("=" * 70)

        breathing_result = calculate_breathing_rate(person_amplitudes, person_timestamps)

        # 5. 結果サマリー
        print("\n" + "=" * 70)
        print("📋 解析結果サマリー")
        print("=" * 70)

        result = {
            "timestamp": datetime.now().isoformat(),
            "base_file": str(base_pcap.name),
            "person_file": str(person_pcap.name),
            "base_packets": len(base_amplitudes),
            "person_packets": len(person_amplitudes),
            "cosine_similarity": similarity,
            "breathing_analysis": breathing_result
        }

        print(f"\n📂 ファイル情報:")
        print(f"   • ベースファイル: {result['base_file']}")
        print(f"   • 人物ファイル: {result['person_file']}")

        print(f"\n📊 データ量:")
        print(f"   • ベースパケット数: {result['base_packets']:,}")
        print(f"   • 人物パケット数: {result['person_packets']:,}")

        print(f"\n📐 コサイン類似度:")
        print(f"   • 類似度スコア: {result['cosine_similarity']:.6f}")
        print(f"   • 類似度(%): {result['cosine_similarity'] * 100:.2f}%")

        print(f"\n🫁 呼吸解析:")
        if breathing_result['breathing_rate']:
            print(f"   • 推定呼吸数: {breathing_result['breathing_rate']:.1f} 回/分")
            print(f"   • 支配周波数: {breathing_result['dominant_frequency']:.3f} Hz")
            print(f"   • 信頼度: {breathing_result['confidence']:.2%}")
        else:
            print(f"   • 推定呼吸数: 検出できませんでした")

        # JSON出力
        output_file = Path(__file__).parent / "breathing_analysis_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n💾 結果を保存しました: {output_file}")

        print("\n" + "=" * 70)
        print("✅ 解析完了！")
        print("=" * 70)

        return 0

    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
