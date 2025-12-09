"""
PCAP解析サービス
Wi-Fi CSIデータをPCAPファイルから抽出・解析する
"""

import logging
import struct
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime
import json

try:
    from scapy.all import rdpcap, Dot11, RadioTap
    from scapy.layers.dot11 import Dot11Beacon, Dot11ProbeReq, Dot11ProbeResp
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
    logging.warning("Scapy not available. PCAP analysis will be limited.")

logger = logging.getLogger(__name__)


class CSIPacket:
    """CSIパケットデータクラス"""

    def __init__(self, timestamp: float, csi_matrix: np.ndarray,
                 rssi: float = 0.0, noise: float = 0.0,
                 rate: int = 0, channel: int = 0):
        self.timestamp = timestamp
        self.csi_matrix = csi_matrix  # Complex CSI matrix
        self.rssi = rssi
        self.noise = noise
        self.rate = rate
        self.channel = channel

    @property
    def amplitude(self) -> np.ndarray:
        """CSI振幅を取得"""
        return np.abs(self.csi_matrix)

    @property
    def phase(self) -> np.ndarray:
        """CSI位相を取得"""
        return np.angle(self.csi_matrix)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'timestamp': self.timestamp,
            'amplitude': self.amplitude.tolist(),
            'phase': self.phase.tolist(),
            'rssi': self.rssi,
            'noise': self.noise,
            'rate': self.rate,
            'channel': self.channel
        }


class PCAPAnalyzer:
    """PCAP解析クラス"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def analyze_pcap_file(self, file_path: str) -> Dict[str, Any]:
        """
        PCAPファイルを解析してCSIデータを抽出

        Args:
            file_path: PCAPファイルのパス

        Returns:
            解析結果辞書
        """
        if not SCAPY_AVAILABLE:
            return self._analyze_with_binary_parser(file_path)

        try:
            return self._analyze_with_scapy(file_path)
        except Exception as e:
            self.logger.warning(f"Scapy analysis failed: {e}, falling back to binary parser")
            return self._analyze_with_binary_parser(file_path)

    def _convert_to_time_series(self, csi_packets: List[CSIPacket]) -> Dict[str, Any]:
        """CSIパケットを時系列データに変換"""
        if not csi_packets:
            return {}

        timestamps = [p.timestamp for p in csi_packets]
        amplitudes = [p.amplitude for p in csi_packets]
        phases = [p.phase for p in csi_packets]
        rssi_values = [p.rssi for p in csi_packets]

        # サブキャリア別時系列データ
        n_subcarriers = len(amplitudes[0]) if amplitudes else 0
        subcarrier_data = {}

        for sc in range(n_subcarriers):
            subcarrier_data[f'subcarrier_{sc}'] = {
                'timestamps': timestamps,
                'amplitudes': [amp[sc] for amp in amplitudes],
                'phases': [phase[sc] for phase in phases]
            }

        return {
            'timestamps': timestamps,
            'rssi': rssi_values,
            'subcarrier_data': subcarrier_data,
            'summary_stats': {
                'n_subcarriers': n_subcarriers,
                'n_samples': len(timestamps),
                'time_range': {
                    'start': min(timestamps) if timestamps else 0,
                    'end': max(timestamps) if timestamps else 0
                }
            }
        }

    def _calculate_duration(self, csi_packets: List[CSIPacket]) -> float:
        """CSIデータの時間範囲を計算"""
        if len(csi_packets) < 2:
            return 0.0

        timestamps = [p.timestamp for p in csi_packets]
        return max(timestamps) - min(timestamps)

    def _calculate_sampling_rate(self, csi_packets: List[CSIPacket]) -> float:
        """平均サンプリングレートを計算"""
        if len(csi_packets) < 2:
            return 0.0

        duration = self._calculate_duration(csi_packets)
        if duration == 0:
            return 0.0

        return len(csi_packets) / duration

    def _extract_channel_info(self, csi_packets: List[CSIPacket]) -> Dict[str, Any]:
        """チャンネル情報を抽出"""
        if not csi_packets:
            return {}

        channels = [p.channel for p in csi_packets if p.channel > 0]
        if not channels:
            return {}

        return {
            'primary_channel': max(set(channels), key=channels.count),
            'all_channels': list(set(channels))
        }


# サービスインスタンス
pcap_analyzer = PCAPAnalyzer()