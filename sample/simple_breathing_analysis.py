#!/usr/bin/env python3
"""
PCAPファイルから直接CSIデータを読み取り、コサイン類似度と呼吸数を計算
"""

import sys
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict

try:
    from scapy.all import rdpcap
    SCAPY_AVAILABLE = True
except ImportError:
    print("❌ scapyが見つかりません。インストールしてください: pip install scapy")
    sys.exit(1)


def read_pcap_packets(pcap_file: Path) -> List:
    """PCAPファイルからパケットを読み取る"""
    print(f"📂 PCAPファイル読み取り: {pcap_file.name}")

    packets = rdpcap(str(pcap_file))
    print(f"   ✓ {len(packets)} パケット読み込み")

    return packets


def extract_csi_from_packets(packets: List) -> Tuple[np.ndarray, List[float]]:
    """
    パケットからCSI類似データを抽出

    注: 実際のCSI情報がパケットに含まれていない場合、
    RSSIや他の無線信号データを代用します
    """
    timestamps = []
    signal_data = []

    for i, packet in enumerate(packets):
        # タイムスタンプ
        if hasattr(packet, 'time'):
            timestamps.append(float(packet.time))
        else:
            timestamps.append(float(i))

        # RadioTapレイヤーからRSSI/信号データを抽出
        signal_values = []

        if packet.haslayer('RadioTap'):
            radiotap = packet.getlayer('RadioTap')

            # dBm_AntSignalフィールド（RSSI）を取得
            if hasattr(radiotap, 'dBm_AntSignal'):
                signal_values.append(abs(radiotap.dBm_AntSignal))

            # Antennaフィールドを取得
            if hasattr(radiotap, 'Antenna'):
                signal_values.append(radiotap.Antenna)

            # Rateフィールドを取得
            if hasattr(radiotap, 'Rate'):
                signal_values.append(radiotap.Rate)

        # 信号データがない場合はゼロで埋める
        if not signal_values:
            signal_values = [0.0] * 10  # ダミーのサブキャリア
        else:
            # 足りない場合は繰り返して64次元に拡張
            while len(signal_values) < 64:
                signal_values.extend(signal_values[:min(len(signal_values), 64 - len(signal_values))])
            signal_values = signal_values[:64]  # 64次元に制限

        signal_data.append(signal_values)

    return np.array(signal_data), timestamps


def calculate_cosine_similarity(vector1: np.ndarray, vector2: np.ndarray) -> float:
    """コサイン類似度を計算"""
    norm1 = np.linalg.norm(vector1)
    norm2 = np.linalg.norm(vector2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    similarity = np.dot(vector1, vector2) / (norm1 * norm2)
    return float(similarity)


def estimate_breathing_rate(signal_data: np.ndarray, timestamps: List[float]) -> Dict:
    """信号データから呼吸数を推定"""
    print("\n🫁 呼吸数推定中...")

    # 各時点での平均信号強度を計算
    mean_signal = np.mean(signal_data, axis=1)

    # サンプリングレート計算
    if len(timestamps) > 1:
        time_diffs = np.diff(timestamps)
        sampling_rate = 1.0 / np.mean(time_diffs) if np.mean(time_diffs) > 0 else 100.0
    else:
        sampling_rate = 100.0

    print(f"   ✓ サンプリングレート: {sampling_rate:.2f} Hz")
    print(f"   ✓ データポイント数: {len(mean_signal)}")

    # FFTで周波数解析
    n = len(mean_signal)
    fft_result = np.fft.fft(mean_signal)
    freqs = np.fft.fftfreq(n, 1/sampling_rate)

    # 正の周波数のみ
    positive_freqs = freqs[:n//2]
    power_spectrum = np.abs(fft_result[:n//2]) ** 2

    # 呼吸の周波数範囲（0.1-0.5 Hz = 6-30 回/分）
    breathing_freq_min = 0.1
    breathing_freq_max = 0.5

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

    # 最大パワーの周波数
    valid_power = power_spectrum[valid_indices]
    valid_frequencies = positive_freqs[valid_indices]

    max_power_idx = np.argmax(valid_power)
    dominant_frequency = valid_frequencies[max_power_idx]
    breathing_rate = dominant_frequency * 60  # Hzから回/分に変換

    # 信頼度計算
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
        "total_samples": len(mean_signal)
    }


def main():
    print("=" * 70)
    print("🔬 CSI呼吸解析 & コサイン類似度計算（簡易版）")
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
        # 1. ベースデータ（人なし）の読み取り
        print("\n" + "=" * 70)
        print("📊 STEP 1: ベースデータ（人なし）の読み取り")
        print("=" * 70)
        base_packets = read_pcap_packets(base_pcap)
        base_signal, base_timestamps = extract_csi_from_packets(base_packets)
        print(f"   ✓ 信号データ形状: {base_signal.shape}")

        # 2. 人物データの読み取り
        print("\n" + "=" * 70)
        print("📊 STEP 2: 人物データの読み取り")
        print("=" * 70)
        person_packets = read_pcap_packets(person_pcap)
        person_signal, person_timestamps = extract_csi_from_packets(person_packets)
        print(f"   ✓ 信号データ形状: {person_signal.shape}")

        # 3. コサイン類似度計算
        print("\n" + "=" * 70)
        print("📐 STEP 3: コサイン類似度計算")
        print("=" * 70)

        # データ数を揃える
        min_samples = min(len(base_signal), len(person_signal))
        base_vector = base_signal[:min_samples].flatten()
        person_vector = person_signal[:min_samples].flatten()

        similarity = calculate_cosine_similarity(base_vector, person_vector)

        print(f"\n   📏 ベクトル次元: {len(base_vector):,}")
        print(f"   🎯 コサイン類似度: {similarity:.6f}")
        print(f"   📊 類似度パーセンテージ: {similarity * 100:.2f}%")

        # 4. 呼吸数推定（人物データ）
        print("\n" + "=" * 70)
        print("🫁 STEP 4: 呼吸数推定（人物データ）")
        print("=" * 70)

        breathing_result = estimate_breathing_rate(person_signal, person_timestamps)

        # 5. 結果サマリー
        print("\n" + "=" * 70)
        print("📋 解析結果サマリー")
        print("=" * 70)

        result = {
            "timestamp": datetime.now().isoformat(),
            "base_file": str(base_pcap.name),
            "person_file": str(person_pcap.name),
            "base_packets": len(base_signal),
            "person_packets": len(person_signal),
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
