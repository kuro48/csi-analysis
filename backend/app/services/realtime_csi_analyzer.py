"""
リアルタイムCSI解析サービス
"""

import numpy as np
import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import asyncio
import logging
from dataclasses import dataclass

from app.services.websocket import realtime_service


@dataclass
class BreathingData:
    """呼吸データ"""
    timestamp: datetime
    breathing_rate: float  # 呼吸数（回/分）
    amplitude: float      # 振幅
    confidence: float     # 信頼度
    raw_signal: List[float]  # 生信号


@dataclass
class CSIAnalysisResult:
    """CSI解析結果"""
    device_id: str
    timestamp: datetime
    breathing_data: BreathingData
    signal_quality: float  # 信号品質
    motion_detected: bool  # 動作検出
    anomaly_score: float   # 異常スコア


class RealtimeCSIAnalyzer:
    """リアルタイムCSI解析器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.analysis_buffer = {}  # デバイス別の解析バッファ
        self.analysis_windows = {}  # デバイス別の解析ウィンドウ
        self.breathing_history = {}  # デバイス別の呼吸履歴

        # 解析パラメータ
        self.sampling_rate = 1000  # Hz
        self.window_size = 30      # 秒
        self.overlap_ratio = 0.5   # オーバーラップ比率
        self.breathing_freq_range = (0.1, 0.5)  # 呼吸周波数範囲（Hz）

    async def analyze_csi_data(self, raw_data: bytes) -> Optional[CSIAnalysisResult]:
        """CSIデータをリアルタイム解析"""
        try:
            # CSIデータを解析形式に変換
            csi_matrix = self._parse_csi_data(raw_data)
            if csi_matrix is None:
                return None

            # デバイス別バッファに追加
            # if device_id not in self.analysis_buffer:
            #     self.analysis_buffer[device_id] = []
            #     self.analysis_windows[device_id] = []
            #     self.breathing_history[device_id] = []

            # self.analysis_buffer[device_id].append({
            #     'timestamp': datetime.utcnow(),
            #     'data': csi_matrix
            # })

            # # バッファサイズ制限
            # max_buffer_size = int(self.window_size * self.sampling_rate / 10)  # 大まかな推定
            # if len(self.analysis_buffer[device_id]) > max_buffer_size:
            #     self.analysis_buffer[device_id] = self.analysis_buffer[device_id][-max_buffer_size:]

            # 解析実行
            analysis_result = await self._perform_analysis(device_id)

            # WebSocketでリアルタイム配信
            if analysis_result:
                await self._broadcast_analysis_result(analysis_result)

            return analysis_result

        except Exception as e:
            self.logger.error(f"CSI解析エラー (device_id: {device_id}): {e}")
            return None

    def _parse_csi_data(self, raw_data: bytes) -> Optional[np.ndarray]:
        """CSI生データを解析用行列に変換"""
        try:
            # 生データの形式に応じて解析
            # ここでは簡単な例として、バイナリデータをfloat配列として解釈
            if len(raw_data) < 4:
                self.logger.warning(f"CSIデータが短すぎます: {len(raw_data)} bytes")
                return None

            # バイナリデータサイズをfloat32（4バイト）の倍数に調整
            element_size = 4  # float32のサイズ
            adjusted_size = (len(raw_data) // element_size) * element_size

            if adjusted_size < element_size:
                self.logger.warning(f"調整後のCSIデータが短すぎます: {adjusted_size} bytes")
                return None

            # 調整されたサイズでバイナリデータをfloat32配列に変換
            adjusted_data = raw_data[:adjusted_size]
            float_array = np.frombuffer(adjusted_data, dtype=np.float32)

            # CSI行列の次元を推定（例：64サブキャリア x 複数タイムスタンプ）
            if len(float_array) < 64:
                # 小さなデータでも動作するよう、利用可能なデータで解析
                num_subcarriers = min(len(float_array), 64)
                if num_subcarriers > 0:
                    csi_matrix = float_array[:num_subcarriers].reshape(1, num_subcarriers)
                    return csi_matrix
                else:
                    return None

            # 64サブキャリアずつに分割
            num_samples = len(float_array) // 64
            csi_matrix = float_array[:num_samples * 64].reshape(num_samples, 64)

            return csi_matrix

        except Exception as e:
            self.logger.error(f"CSIデータパース エラー: {e}")
            return None

    async def _perform_analysis(self, device_id: str) -> Optional[CSIAnalysisResult]:
        """CSI解析実行"""
        try:
            buffer = self.analysis_buffer[device_id]
            if len(buffer) < 10:  # 最小データ数チェック
                return None

            # 時系列データ抽出
            timestamps = [item['timestamp'] for item in buffer]
            csi_matrices = [item['data'] for item in buffer]

            # CSI振幅時系列を抽出
            amplitude_series = self._extract_amplitude_series(csi_matrices)

            # 呼吸解析
            breathing_data = self._analyze_breathing(amplitude_series, timestamps[-1])

            # 信号品質評価
            signal_quality = self._evaluate_signal_quality(amplitude_series)

            # 動作検出
            motion_detected = self._detect_motion(amplitude_series)

            # 異常検出
            anomaly_score = self._detect_anomaly(device_id, breathing_data)

            result = CSIAnalysisResult(
                device_id=device_id,
                timestamp=timestamps[-1],
                breathing_data=breathing_data,
                signal_quality=signal_quality,
                motion_detected=motion_detected,
                anomaly_score=anomaly_score
            )

            # 履歴に追加
            self.breathing_history[device_id].append(breathing_data)
            if len(self.breathing_history[device_id]) > 100:  # 履歴サイズ制限
                self.breathing_history[device_id] = self.breathing_history[device_id][-100:]

            return result

        except Exception as e:
            self.logger.error(f"CSI解析実行エラー (device_id: {device_id}): {e}")
            return None

    def _extract_amplitude_series(self, csi_matrices: List[np.ndarray]) -> np.ndarray:
        """CSI振幅時系列を抽出"""
        try:
            # 各時刻でのCSI振幅を計算
            amplitudes = []
            for matrix in csi_matrices:
                # 複素数の場合は振幅を取得、実数の場合はそのまま
                if np.iscomplexobj(matrix):
                    amp = np.abs(matrix)
                else:
                    amp = np.abs(matrix)

                # 全サブキャリアの振幅平均を取得
                mean_amplitude = np.mean(amp)
                amplitudes.append(mean_amplitude)

            return np.array(amplitudes)

        except Exception as e:
            self.logger.error(f"振幅時系列抽出エラー: {e}")
            return np.array([])

    def _analyze_breathing(self, amplitude_series: np.ndarray, timestamp: datetime) -> BreathingData:
        """呼吸解析"""
        try:
            if len(amplitude_series) < 10:
                return BreathingData(
                    timestamp=timestamp,
                    breathing_rate=0.0,
                    amplitude=0.0,
                    confidence=0.0,
                    raw_signal=amplitude_series.tolist()
                )

            # 前処理：ハイパスフィルタで低周波成分除去
            filtered_signal = self._highpass_filter(amplitude_series, cutoff=0.05)

            # FFT で周波数解析
            freqs, power_spectrum = self._compute_power_spectrum(filtered_signal)

            # 呼吸周波数帯域でピーク検出
            breathing_freq, breathing_power = self._find_breathing_peak(freqs, power_spectrum)

            # 呼吸数計算（回/分）
            breathing_rate = breathing_freq * 60.0 if breathing_freq > 0 else 0.0

            # 振幅と信頼度計算
            amplitude = np.sqrt(breathing_power)
            confidence = self._calculate_confidence(power_spectrum, breathing_freq)

            return BreathingData(
                timestamp=timestamp,
                breathing_rate=breathing_rate,
                amplitude=amplitude,
                confidence=confidence,
                raw_signal=filtered_signal.tolist()[-50:]  # 最新50サンプル
            )

        except Exception as e:
            self.logger.error(f"呼吸解析エラー: {e}")
            return BreathingData(
                timestamp=timestamp,
                breathing_rate=0.0,
                amplitude=0.0,
                confidence=0.0,
                raw_signal=[]
            )

    def _highpass_filter(self, signal: np.ndarray, cutoff: float) -> np.ndarray:
        """簡単なハイパスフィルタ"""
        try:
            # 移動平均による低周波成分除去
            window_size = max(3, len(signal) // 10)
            if len(signal) < window_size:
                return signal

            moving_avg = np.convolve(signal, np.ones(window_size)/window_size, mode='same')
            return signal - moving_avg

        except Exception:
            return signal

    def _compute_power_spectrum(self, signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """パワースペクトラム計算"""
        try:
            # FFT実行
            fft_result = np.fft.fft(signal)
            freqs = np.fft.fftfreq(len(signal), d=1.0)  # 正規化周波数

            # パワースペクトラム
            power_spectrum = np.abs(fft_result) ** 2

            # 正の周波数のみ
            positive_freq_idx = freqs >= 0
            freqs = freqs[positive_freq_idx]
            power_spectrum = power_spectrum[positive_freq_idx]

            return freqs, power_spectrum

        except Exception as e:
            self.logger.error(f"パワースペクトラム計算エラー: {e}")
            return np.array([]), np.array([])

    def _find_breathing_peak(self, freqs: np.ndarray, power_spectrum: np.ndarray) -> Tuple[float, float]:
        """呼吸周波数ピーク検出"""
        try:
            if len(freqs) == 0 or len(power_spectrum) == 0:
                return 0.0, 0.0

            # 呼吸周波数帯域のマスク
            breathing_mask = (freqs >= self.breathing_freq_range[0]) & (freqs <= self.breathing_freq_range[1])

            if not np.any(breathing_mask):
                return 0.0, 0.0

            # 呼吸帯域でのピーク検出
            breathing_freqs = freqs[breathing_mask]
            breathing_power = power_spectrum[breathing_mask]

            if len(breathing_power) == 0:
                return 0.0, 0.0

            # 最大パワーの周波数を呼吸周波数とする
            peak_idx = np.argmax(breathing_power)
            breathing_freq = breathing_freqs[peak_idx]
            breathing_power_value = breathing_power[peak_idx]

            return float(breathing_freq), float(breathing_power_value)

        except Exception as e:
            self.logger.error(f"呼吸ピーク検出エラー: {e}")
            return 0.0, 0.0

    def _calculate_confidence(self, power_spectrum: np.ndarray, breathing_freq: float) -> float:
        """信頼度計算"""
        try:
            if len(power_spectrum) == 0 or breathing_freq == 0:
                return 0.0

            # 呼吸ピークのパワーと全体パワーの比
            total_power = np.sum(power_spectrum)
            if total_power == 0:
                return 0.0

            # 呼吸周波数周辺のパワー
            # 簡単な実装として、ピーク周辺の平均パワーを使用
            peak_power = np.max(power_spectrum)
            confidence = min(1.0, peak_power / (total_power / len(power_spectrum)))

            return float(confidence)

        except Exception:
            return 0.0

    def _evaluate_signal_quality(self, amplitude_series: np.ndarray) -> float:
        """信号品質評価"""
        try:
            if len(amplitude_series) == 0:
                return 0.0

            # SNR の簡易推定
            signal_std = np.std(amplitude_series)
            signal_mean = np.mean(np.abs(amplitude_series))

            if signal_mean == 0:
                return 0.0

            # SNR的な指標
            quality = min(1.0, signal_std / signal_mean)
            return float(quality)

        except Exception:
            return 0.0

    def _detect_motion(self, amplitude_series: np.ndarray) -> bool:
        """動作検出"""
        try:
            if len(amplitude_series) < 5:
                return False

            # 振幅の急激な変化を動作として検出
            diff = np.diff(amplitude_series)
            motion_threshold = np.std(amplitude_series) * 2

            large_changes = np.abs(diff) > motion_threshold
            return bool(np.any(large_changes))

        except Exception:
            return False

    def _detect_anomaly(self, device_id: str, breathing_data: BreathingData) -> float:
        """異常検出"""
        try:
            # 呼吸数の異常検出
            normal_breathing_range = (12, 20)  # 正常な呼吸数範囲（回/分）

            anomaly_score = 0.0

            # 呼吸数異常
            if breathing_data.breathing_rate < normal_breathing_range[0]:
                anomaly_score += 0.3  # 徐呼吸
            elif breathing_data.breathing_rate > normal_breathing_range[1]:
                anomaly_score += 0.3  # 頻呼吸

            # 信頼度が低い場合
            if breathing_data.confidence < 0.3:
                anomaly_score += 0.2

            # 履歴との比較
            if device_id in self.breathing_history and len(self.breathing_history[device_id]) > 5:
                recent_rates = [b.breathing_rate for b in self.breathing_history[device_id][-5:]]
                if len(recent_rates) > 0:
                    avg_rate = np.mean(recent_rates)
                    if abs(breathing_data.breathing_rate - avg_rate) > 5:  # 急激な変化
                        anomaly_score += 0.2

            return min(1.0, anomaly_score)

        except Exception:
            return 0.0

    async def _broadcast_analysis_result(self, result: CSIAnalysisResult):
        """解析結果をWebSocketでブロードキャスト"""
        try:
            message_data = {
                "type": "csi_analysis",
                "device_id": result.device_id,
                "timestamp": result.timestamp.isoformat(),
                "breathing_rate": result.breathing_data.breathing_rate,
                "breathing_amplitude": result.breathing_data.amplitude,
                "breathing_confidence": result.breathing_data.confidence,
                "signal_quality": result.signal_quality,
                "motion_detected": result.motion_detected,
                "anomaly_score": result.anomaly_score,
                "raw_signal": result.breathing_data.raw_signal[-20:]  # 最新20サンプル
            }

            await realtime_service.broadcast_csi_analysis(result.device_id, message_data)

        except Exception as e:
            self.logger.error(f"解析結果ブロードキャストエラー: {e}")


# グローバルインスタンス
realtime_analyzer = RealtimeCSIAnalyzer()