#!/usr/bin/env python3
"""
PCAP CSIデータ抽出スクリプト

PCAPファイルからCSI振幅データを抽出し、CSV形式で保存します。
ZKP証明生成のための前処理として使用します。
"""

import sys
import os
import csv
import json
import numpy as np
from pathlib import Path

# バックエンドディレクトリをパスに追加
BACKEND_DIR = Path(__file__).parent.parent.parent / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

from app.services.pcap_analyzer import pcap_analyzer


def extract_csi_amplitudes(pcap_path: str, output_csv: str, num_packets: int = 10):
    """
    PCAPファイルからCSI振幅データを抽出してCSVに保存

    Args:
        pcap_path: PCAPファイルのパス
        output_csv: 出力CSVファイルのパス
        num_packets: 抽出するパケット数
    """
    print(f"📂 Analyzing PCAP file: {pcap_path}")

    # PCAP解析
    result = pcap_analyzer.analyze_pcap_file(pcap_path)

    csi_packets = result.get('csi_packets', [])

    if not csi_packets:
        print("❌ No CSI packets found in PCAP file")
        print("   Generating mock CSI data for demonstration...")

        # モックデータ生成
        mock_amplitudes = generate_mock_csi_data(num_packets)
        save_to_csv(mock_amplitudes, output_csv)
        return mock_amplitudes

    print(f"✅ Found {len(csi_packets)} CSI packets")

    # 振幅データを抽出（最初のnum_packetsパケット）
    amplitudes_list = []
    for i, packet in enumerate(csi_packets[:num_packets]):
        amplitude = packet.get('amplitude', [])
        if amplitude:
            amplitudes_list.append(amplitude)

    print(f"   Extracted {len(amplitudes_list)} packets with amplitude data")

    # CSVに保存
    save_to_csv(amplitudes_list, output_csv)

    return amplitudes_list


def generate_mock_csi_data(num_packets: int = 10, num_subcarriers: int = 64):
    """
    モックCSI振幅データを生成

    実際のWi-Fi CSI信号の特性を模倣：
    - 周波数選択性フェージング
    - サブキャリアごとの異なる振幅パターン
    - 時間変動（呼吸による微小な変化を含む）
    """
    print(f"   Generating {num_packets} packets of mock CSI data...")

    amplitudes_list = []

    # 呼吸周波数（0.3 Hz = 18 bpm）
    breathing_freq = 0.3
    time_interval = 0.01  # 10msサンプリング

    for packet_idx in range(num_packets):
        # 時間依存の呼吸成分
        t = packet_idx * time_interval
        breathing_component = 0.1 * np.sin(2 * np.pi * breathing_freq * t)

        # サブキャリアごとの振幅（周波数選択性フェージング）
        amplitudes = []
        for sc in range(num_subcarriers):
            # ベース振幅（フェージング特性）
            base_amp = 0.5 + 0.5 * np.cos(2 * np.pi * sc / num_subcarriers)

            # 呼吸による微小変化を追加
            breathing_effect = breathing_component * (1 + 0.1 * np.cos(2 * np.pi * sc / 8))

            # ノイズ
            noise = np.random.normal(0, 0.05)

            # 最終振幅
            amplitude = base_amp + breathing_effect + noise
            amplitudes.append(max(0.01, amplitude))  # 正の値を保証

        amplitudes_list.append(amplitudes)

    return amplitudes_list


def save_to_csv(amplitudes_list, output_csv: str):
    """
    CSI振幅データをCSVに保存

    CSV形式:
    packet_id,subcarrier_0,subcarrier_1,...,subcarrier_63
    0,0.85,1.23,...,0.67
    1,0.87,1.21,...,0.69
    ...
    """
    print(f"💾 Saving CSI data to CSV: {output_csv}")

    with open(output_csv, 'w', newline='') as f:
        writer = csv.writer(f)

        # ヘッダー
        num_subcarriers = len(amplitudes_list[0]) if amplitudes_list else 64
        header = ['packet_id'] + [f'subcarrier_{i}' for i in range(num_subcarriers)]
        writer.writerow(header)

        # データ行
        for packet_id, amplitudes in enumerate(amplitudes_list):
            row = [packet_id] + amplitudes
            writer.writerow(row)

    print(f"✅ Saved {len(amplitudes_list)} packets to CSV")

    # サマリー情報も保存
    summary = {
        'num_packets': len(amplitudes_list),
        'num_subcarriers': num_subcarriers,
        'csv_file': output_csv,
        'statistics': {
            'mean_amplitude': float(np.mean(amplitudes_list)),
            'std_amplitude': float(np.std(amplitudes_list)),
            'min_amplitude': float(np.min(amplitudes_list)),
            'max_amplitude': float(np.max(amplitudes_list))
        }
    }

    summary_file = output_csv.replace('.csv', '_summary.json')
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"   Summary: {summary_file}")
    print(f"   Mean amplitude: {summary['statistics']['mean_amplitude']:.4f}")
    print(f"   Std amplitude: {summary['statistics']['std_amplitude']:.4f}")


def main():
    """メイン処理"""
    # パス設定
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent

    pcap_file = project_root / 'sample' / 'data' / 'csi_data_20250930_122219.pcap'
    output_csv = script_dir.parent / 'data' / 'csi_amplitudes.csv'

    # 出力ディレクトリ作成
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("CSI Data Extraction from PCAP")
    print("=" * 60)
    print()

    if not pcap_file.exists():
        print(f"❌ PCAP file not found: {pcap_file}")
        sys.exit(1)

    # CSIデータ抽出
    amplitudes = extract_csi_amplitudes(str(pcap_file), str(output_csv), num_packets=10)

    print()
    print("=" * 60)
    print("✅ CSI extraction complete!")
    print("=" * 60)
    print(f"\nNext step: Use the CSV file for ZKP proof generation")
    print(f"  node scripts/prove_from_csv.js")


if __name__ == '__main__':
    main()
