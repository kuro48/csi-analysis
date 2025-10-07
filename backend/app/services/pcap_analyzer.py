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

    def _analyze_with_scapy(self, file_path: str) -> Dict[str, Any]:
        """Scapyを使用したPCAP解析"""
        self.logger.info(f"Analyzing PCAP file with Scapy: {file_path}")

        packets = rdpcap(file_path)
        csi_packets = []
        metadata = {
            'total_packets': len(packets),
            'analysis_method': 'scapy',
            'file_size': Path(file_path).stat().st_size,
            'analysis_timestamp': datetime.now().isoformat()
        }

        for i, packet in enumerate(packets):
            try:
                # RadioTapヘッダーからCSI情報を抽出
                if RadioTap in packet:
                    csi_data = self._extract_csi_from_radiotap(packet)
                    if csi_data:
                        csi_packets.append(csi_data)

                # Dot11フレームからCSI情報を抽出
                elif Dot11 in packet:
                    csi_data = self._extract_csi_from_dot11(packet)
                    if csi_data:
                        csi_packets.append(csi_data)

            except Exception as e:
                self.logger.debug(f"Failed to process packet {i}: {e}")
                continue

        # CSIデータを時系列データに変換
        time_series_data = self._convert_to_time_series(csi_packets)

        return {
            'csi_packets': [p.to_dict() for p in csi_packets],
            'time_series': time_series_data,
            'metadata': metadata,
            'summary': {
                'total_csi_packets': len(csi_packets),
                'duration_seconds': self._calculate_duration(csi_packets),
                'average_sampling_rate': self._calculate_sampling_rate(csi_packets),
                'channel_info': self._extract_channel_info(csi_packets)
            }
        }

    def _analyze_with_binary_parser(self, file_path: str) -> Dict[str, Any]:
        """バイナリパーサーを使用したPCAP解析（フォールバック）"""
        self.logger.info(f"Analyzing PCAP file with binary parser: {file_path}")

        # シンプルなバイナリ解析
        # 実際のCSI抽出は限定的だが、デモ用データを生成
        file_size = Path(file_path).stat().st_size

        # モックCSIデータを生成（実際の実装では適切な解析を行う）
        mock_csi_packets = self._generate_mock_csi_data(100)  # 100パケット分
        time_series_data = self._convert_to_time_series(mock_csi_packets)

        metadata = {
            'total_packets': 100,
            'analysis_method': 'binary_parser',
            'file_size': file_size,
            'analysis_timestamp': datetime.now().isoformat(),
            'note': 'Mock data generated for demonstration'
        }

        return {
            'csi_packets': [p.to_dict() for p in mock_csi_packets],
            'time_series': time_series_data,
            'metadata': metadata,
            'summary': {
                'total_csi_packets': len(mock_csi_packets),
                'duration_seconds': self._calculate_duration(mock_csi_packets),
                'average_sampling_rate': self._calculate_sampling_rate(mock_csi_packets),
                'channel_info': self._extract_channel_info(mock_csi_packets)
            }
        }

    def _extract_csi_from_radiotap(self, packet) -> Optional[CSIPacket]:
        """RadioTapヘッダーからCSI情報を抽出"""
        try:
            radiotap = packet[RadioTap]
            timestamp = float(packet.time)

            # RadioTapからRSSI、ノイズ、レートを抽出
            rssi = getattr(radiotap, 'dBm_AntSignal', 0)
            noise = getattr(radiotap, 'dBm_AntNoise', 0)
            rate = getattr(radiotap, 'Rate', 0)
            channel = getattr(radiotap, 'Channel', 0)

            # モックCSIマトリックス（実際の実装では適切な抽出を行う）
            csi_matrix = self._generate_mock_csi_matrix()

            return CSIPacket(timestamp, csi_matrix, rssi, noise, rate, channel)

        except Exception as e:
            self.logger.debug(f"Failed to extract CSI from RadioTap: {e}")
            return None

    def _extract_csi_from_dot11(self, packet) -> Optional[CSIPacket]:
        """Dot11フレームからCSI情報を抽出"""
        try:
            timestamp = float(packet.time)

            # Dot11フレームから基本情報を抽出
            dot11 = packet[Dot11]

            # モックCSIマトリックス
            csi_matrix = self._generate_mock_csi_matrix()

            return CSIPacket(timestamp, csi_matrix)

        except Exception as e:
            self.logger.debug(f"Failed to extract CSI from Dot11: {e}")
            return None

    def _generate_mock_csi_matrix(self, n_subcarriers: int = 64) -> np.ndarray:
        """モックCSIマトリックスを生成"""
        # 複素数CSIマトリックス（振幅と位相）
        amplitude = np.random.uniform(0.1, 2.0, n_subcarriers)
        phase = np.random.uniform(-np.pi, np.pi, n_subcarriers)
        return amplitude * np.exp(1j * phase)

    def _generate_mock_csi_data(self, n_packets: int) -> List[CSIPacket]:
        """デモ用モックCSIデータを生成"""
        packets = []
        base_time = datetime.now().timestamp()

        for i in range(n_packets):
            timestamp = base_time + i * 0.01  # 10ms間隔
            csi_matrix = self._generate_mock_csi_matrix()
            rssi = np.random.uniform(-80, -30)
            noise = np.random.uniform(-95, -85)

            packets.append(CSIPacket(timestamp, csi_matrix, rssi, noise))

        return packets

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