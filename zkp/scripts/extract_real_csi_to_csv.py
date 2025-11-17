#!/usr/bin/env python3
"""
実際のPCAPファイルからCSIデータを抽出してFFT処理を行う

CSIデータの抽出 → FFT → 周波数成分 → CSV保存
"""

import sys
import csv
import json
import struct
import numpy as np
from pathlib import Path
from scapy.all import rdpcap, Raw
from scipy.fft import fft, fftfreq


def parse_csi_from_raw_data(raw_bytes):
    """
    Rawバイトデータから CSI 値を抽出

    NEXMON/ESP32 CSI フォーマット想定:
    - 複素数CSI値が16ビット符号付き整数で格納
    - 実部・虚部が交互に配置
    """
    # ヘッダースキップ（最初の16バイトをヘッダーと仮定）
    header_size = 16
    csi_data_bytes = raw_bytes[header_size:]

    # 16ビット符号付き整数として解釈
    # '<h' = little-endian signed short (int16)
    num_values = len(csi_data_bytes) // 2
    csi_raw_values = struct.unpack(f'<{num_values}h', csi_data_bytes[:num_values*2])

    # 実部と虚部のペアから複素数CSIを生成
    csi_complex = []
    for i in range(0, len(csi_raw_values) - 1, 2):
        real = csi_raw_values[i]
        imag = csi_raw_values[i + 1]
        csi_complex.append(complex(real, imag))

    return np.array(csi_complex)


def extract_csi_from_pcap(pcap_path, max_packets=100):
    """
    PCAPファイルから実際のCSIデータを抽出
    """
    print(f"📂 Loading PCAP file: {pcap_path}")

    try:
        packets = rdpcap(pcap_path)
        print(f"   Total packets in PCAP: {len(packets)}")
    except Exception as e:
        raise Exception(f"Failed to read PCAP file: {e}")

    csi_packets = []

    for i, packet in enumerate(packets[:max_packets]):
        if Raw not in packet:
            continue

        try:
            raw_data = bytes(packet[Raw].load)

            # CSIデータを抽出
            csi_complex = parse_csi_from_raw_data(raw_data)

            if len(csi_complex) > 0:
                # CSI振幅を計算
                csi_amplitude = np.abs(csi_complex)

                csi_packets.append({
                    'packet_id': i,
                    'timestamp': float(packet.time),
                    'csi_complex': csi_complex,
                    'csi_amplitude': csi_amplitude
                })

        except Exception as e:
            print(f"   Warning: Failed to parse packet {i}: {e}")
            continue

    print(f"✅ Extracted CSI data from {len(csi_packets)} packets")

    if len(csi_packets) == 0:
        raise Exception("No CSI data could be extracted from PCAP file")

    # サブキャリア数を表示
    if csi_packets:
        num_subcarriers = len(csi_packets[0]['csi_amplitude'])
        print(f"   Subcarriers per packet: {num_subcarriers}")

    return csi_packets


def apply_fft_to_csi(csi_packets, sampling_rate=100):
    """
    CSI振幅時系列データにFFTを適用して周波数成分を抽出

    Args:
        csi_packets: CSIパケットリスト
        sampling_rate: サンプリングレート (Hz)

    Returns:
        周波数成分データ（サブキャリアごと）
    """
    print(f"\n🔬 Applying FFT to CSI amplitude data...")
    print(f"   Sampling rate: {sampling_rate} Hz")

    num_packets = len(csi_packets)
    num_subcarriers = len(csi_packets[0]['csi_amplitude'])

    # サブキャリアごとに時系列データを構築
    subcarrier_timeseries = []
    for sc_idx in range(num_subcarriers):
        timeseries = [packet['csi_amplitude'][sc_idx] for packet in csi_packets]
        subcarrier_timeseries.append(timeseries)

    # 各サブキャリアにFFTを適用
    fft_results = []
    for sc_idx, timeseries in enumerate(subcarrier_timeseries):
        # FFT実行
        fft_values = fft(timeseries)

        # パワースペクトル（振幅の二乗）
        power_spectrum = np.abs(fft_values) ** 2

        # 周波数軸
        freqs = fftfreq(num_packets, d=1.0/sampling_rate)

        # 正の周波数のみ
        positive_freq_idx = freqs > 0
        positive_freqs = freqs[positive_freq_idx]
        positive_power = power_spectrum[positive_freq_idx]

        fft_results.append({
            'subcarrier_id': sc_idx,
            'frequencies': positive_freqs,
            'power_spectrum': positive_power,
            'peak_freq': positive_freqs[np.argmax(positive_power)] if len(positive_power) > 0 else 0,
            'peak_power': np.max(positive_power) if len(positive_power) > 0 else 0
        })

    print(f"✅ FFT completed for {num_subcarriers} subcarriers")

    # FFT結果のサマリーを表示
    peak_freqs = [r['peak_freq'] for r in fft_results]
    print(f"   Peak frequency range: {min(peak_freqs):.2f} - {max(peak_freqs):.2f} Hz")

    return fft_results


def save_fft_results_to_csv(fft_results, output_csv):
    """
    FFT結果（周波数成分）をCSVに保存

    CSV形式:
    subcarrier_id,freq_0,freq_1,...,freq_N,peak_freq,peak_power
    """
    print(f"\n💾 Saving FFT results to CSV: {output_csv}")

    with open(output_csv, 'w', newline='') as f:
        writer = csv.writer(f)

        # ヘッダー（周波数ビン + メタデータ）
        num_freq_bins = len(fft_results[0]['power_spectrum'])
        header = ['subcarrier_id']
        header += [f'power_bin_{i}' for i in range(num_freq_bins)]
        header += ['peak_freq', 'peak_power']
        writer.writerow(header)

        # データ行
        for result in fft_results:
            row = [result['subcarrier_id']]
            row += result['power_spectrum'].tolist()
            row += [result['peak_freq'], result['peak_power']]
            writer.writerow(row)

    print(f"✅ Saved FFT results for {len(fft_results)} subcarriers")

    # サマリーも保存
    summary = {
        'num_subcarriers': len(fft_results),
        'num_frequency_bins': len(fft_results[0]['power_spectrum']),
        'frequency_range': {
            'min': float(min(r['frequencies'][0] for r in fft_results if len(r['frequencies']) > 0)),
            'max': float(max(r['frequencies'][-1] for r in fft_results if len(r['frequencies']) > 0))
        },
        'peak_frequencies': {
            'min': float(min(r['peak_freq'] for r in fft_results)),
            'max': float(max(r['peak_freq'] for r in fft_results)),
            'mean': float(np.mean([r['peak_freq'] for r in fft_results]))
        },
        'peak_powers': {
            'min': float(min(r['peak_power'] for r in fft_results)),
            'max': float(max(r['peak_power'] for r in fft_results)),
            'mean': float(np.mean([r['peak_power'] for r in fft_results]))
        }
    }

    summary_file = output_csv.replace('.csv', '_summary.json')
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"   Summary: {summary_file}")
    print(f"   Peak frequency range: {summary['peak_frequencies']['min']:.2f} - {summary['peak_frequencies']['max']:.2f} Hz")


def main():
    """メイン処理"""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent

    pcap_file = project_root / 'sample' / 'data' / 'csi_data_20250930_122219.pcap'
    output_csv = script_dir.parent / 'data' / 'csi_fft_real.csv'

    # 出力ディレクトリ作成
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Real CSI Data Extraction with FFT")
    print("=" * 60)
    print()

    if not pcap_file.exists():
        print(f"❌ PCAP file not found: {pcap_file}")
        sys.exit(1)

    try:
        # 1. PCAPファイルから実際のCSIデータを抽出
        csi_packets = extract_csi_from_pcap(str(pcap_file), max_packets=100)

        # 2. FFTで周波数成分を計算
        fft_results = apply_fft_to_csi(csi_packets, sampling_rate=100)

        # 3. FFT結果をCSVに保存
        save_fft_results_to_csv(fft_results, str(output_csv))

        print()
        print("=" * 60)
        print("✅ Real CSI extraction and FFT complete!")
        print("=" * 60)
        print(f"\nNext step: Use the FFT CSV for ZKP proof generation")
        print(f"  node scripts/prove_from_fft_csv.js")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
