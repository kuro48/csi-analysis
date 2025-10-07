#!/usr/bin/env python3
"""
サンプルCSIデータ生成スクリプト
Wi-Fi CSI（Channel State Information）をシミュレートした呼吸監視用サンプルデータを生成
"""

import numpy as np
import struct
import os
from datetime import datetime

def generate_breathing_signal(duration=30, sampling_rate=1000, breathing_rate=15):
    """
    呼吸信号をシミュレート

    Args:
        duration: 信号の長さ（秒）
        sampling_rate: サンプリングレート（Hz）
        breathing_rate: 呼吸数（回/分）

    Returns:
        呼吸に対応する振幅変調信号
    """
    t = np.linspace(0, duration, duration * sampling_rate)

    # 基本の呼吸周波数（Hz）
    breath_freq = breathing_rate / 60.0

    # 呼吸による振幅変調（主要な呼吸周波数 + 高調波）
    breath_signal = (
        np.sin(2 * np.pi * breath_freq * t) +  # 基本波
        0.3 * np.sin(2 * np.pi * breath_freq * 2 * t) +  # 第二高調波
        0.1 * np.sin(2 * np.pi * breath_freq * 3 * t)    # 第三高調波
    )

    # ランダムノイズを追加
    noise = 0.1 * np.random.randn(len(t))

    return breath_signal + noise

def generate_csi_data(num_subcarriers=64, duration=30, sampling_rate=100):
    """
    CSIデータをシミュレート

    Args:
        num_subcarriers: サブキャリア数
        duration: 信号の長さ（秒）
        sampling_rate: サンプリングレート（Hz）

    Returns:
        CSI行列（time x subcarriers）
    """
    num_samples = duration * sampling_rate

    # 呼吸信号を生成
    breathing_signal = generate_breathing_signal(duration, sampling_rate, breathing_rate=16)

    # CSI行列初期化
    csi_matrix = np.zeros((num_samples, num_subcarriers), dtype=np.complex64)

    for sc in range(num_subcarriers):
        # 各サブキャリアの基本特性
        base_amplitude = 1.0 + 0.5 * np.random.randn()  # 基本振幅
        base_phase = 2 * np.pi * np.random.rand()       # 基本位相

        # 呼吸による変調の感度（中央付近のサブキャリアが敏感）
        sensitivity = np.exp(-((sc - num_subcarriers/2) / (num_subcarriers/4))**2)

        # 時間変化する振幅と位相
        amplitude = base_amplitude * (1 + 0.05 * sensitivity * breathing_signal)
        phase = base_phase + 0.02 * sensitivity * breathing_signal

        # 複素CSI値
        csi_matrix[:, sc] = amplitude * np.exp(1j * phase)

        # さらにノイズを追加
        noise_real = 0.05 * np.random.randn(num_samples)
        noise_imag = 0.05 * np.random.randn(num_samples)
        csi_matrix[:, sc] += noise_real + 1j * noise_imag

    return csi_matrix

def save_csi_binary(csi_data, filename):
    """
    CSIデータをバイナリ形式で保存
    """
    with open(filename, 'wb') as f:
        # ヘッダー情報
        num_samples, num_subcarriers = csi_data.shape
        f.write(struct.pack('I', num_samples))       # サンプル数
        f.write(struct.pack('I', num_subcarriers))   # サブキャリア数
        f.write(struct.pack('I', 100))               # サンプリングレート

        # CSIデータ（実部と虚部を交互に保存）
        for sample in range(num_samples):
            for sc in range(num_subcarriers):
                complex_val = csi_data[sample, sc]
                f.write(struct.pack('f', complex_val.real))
                f.write(struct.pack('f', complex_val.imag))

def main():
    """メイン処理"""
    # 出力ディレクトリ作成
    output_dir = "/Users/ryunosukekurokawa/Documents/class/lab/M1/研究関連/csi-web-platform/sample"
    os.makedirs(output_dir, exist_ok=True)

    print("サンプルCSIデータを生成中...")

    # 複数のシナリオでサンプルデータを生成
    scenarios = [
        {"name": "normal_breathing", "duration": 30, "breathing_rate": 16, "desc": "正常呼吸"},
        {"name": "slow_breathing", "duration": 30, "breathing_rate": 10, "desc": "ゆっくり呼吸"},
        {"name": "fast_breathing", "duration": 30, "breathing_rate": 25, "desc": "早い呼吸"},
        {"name": "irregular_breathing", "duration": 60, "breathing_rate": 18, "desc": "不規則呼吸"}
    ]

    for scenario in scenarios:
        print(f"  {scenario['desc']} データ生成中...")

        # CSIデータ生成
        if scenario['name'] == 'irregular_breathing':
            # 不規則呼吸の場合は変動を追加
            csi_data = generate_csi_data(
                num_subcarriers=64,
                duration=scenario['duration'],
                sampling_rate=100
            )
            # 呼吸レートの変動を追加
            variation = np.random.uniform(0.8, 1.2, csi_data.shape[0])
            for i in range(csi_data.shape[0]):
                csi_data[i, :] *= variation[i]
        else:
            csi_data = generate_csi_data(
                num_subcarriers=64,
                duration=scenario['duration'],
                sampling_rate=100
            )

        # ファイル保存
        filename = os.path.join(output_dir, f"sample_csi_{scenario['name']}.bin")
        save_csi_binary(csi_data, filename)

        print(f"    保存: {filename}")
        print(f"    形状: {csi_data.shape}")
        print(f"    ファイルサイズ: {os.path.getsize(filename)} bytes")

    print("\nサンプルCSIデータ生成完了!")
    print(f"出力ディレクトリ: {output_dir}")

if __name__ == "__main__":
    main()