"""
PCAP解析サービス
Wi-Fi CSIデータをPCAPファイルから抽出・解析する
"""

from CSIKit.reader import get_reader
from CSIKit.util import csitools


import logging
import struct
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime
import json

try:
    from scapy.all import rdpcap
    from scapy.layers.dot11 import Dot11Beacon, Dot11ProbeReq, Dot11ProbeResp
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
    logging.warning("Scapy not available. PCAP analysis will be limited.")

logger = logging.getLogger(__name__)

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

        my_reader = get_reader(file_path)
        csi_data = my_reader.read_file(file_path, scaled=True)
        si_matrix, no_frames, no_subcarriers = csitools.get_CSI(csi_data)
        print(si_matrix)
        print(no_frames)
        print(no_subcarriers)

        # try:
        #     packets = rdpcap(file_path)
        #     timestamps = [pkt.time for pkt in packets if pkt.haslayer('UDP')]
        # except FileNotFoundError:
        #     print(f"Error: PCAP file not found at {file_path}")
        #     return []
        # except Exception as e:
        #     print(f"Error reading or processing PCAP file {file_path}: {e}")
        #     return []
        


    # def save_initial_data(df, output_dir, input_base):
    #     base_name_for_file = os.path.basename(input_base)
    #     initial_file = os.path.join(output_dir, f"{base_name_for_file}_initial_processed.csv")
    #     df.to_csv(initial_file, index=False)
    #     print(f"Initial processed data saved to {initial_file}")
        
    #     plot_file = os.path.join(output_dir, f"{base_name_for_file}_initial_plot.png")
    #     plot_time_series_from_dataframe(df, plot_file, "Initial Processed")

    # def make_bins(max_val, step):
    #     if step <= 0:
    #         raise ValueError("Step must be positive")
    #     num_steps = int(max_val / step)
    #     return [i * step for i in range(num_steps + 1)]

    # def drop_invalid_rows(df):
    #     if df is None or df.empty:
    #         return pd.DataFrame()
    #     numeric_cols = df.select_dtypes(include=[np.number]).columns
    #     if not numeric_cols.any():
    #         return df 
    #     df_cleaned = df.dropna(subset=numeric_cols, how='any')
    #     df_cleaned = df_cleaned[~df_cleaned[numeric_cols].isin([np.inf, -np.inf]).any(axis=1)]
    #     return df_cleaned

    # def normalize_signal(signal):
    #     if len(signal) == 0:
    #         return signal
    #     signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
    #     mean = np.mean(signal)
    #     std = np.std(signal)
    #     if std == 0:
    #         return signal - mean
    #     return (signal - mean) / std

    # def contains_nan_or_inf(array):
    #     arr = np.asarray(array)
    #     return np.isnan(arr).any() or np.isinf(arr).any()

    # def _bandpass_filter(data, lowcut, highcut, fs, order=Config.FILTER_ORDER):
    #     nyquist = 0.5 * fs
    #     low = lowcut / nyquist
    #     high = highcut / nyquist
    #     low = max(1e-9, low) 
    #     high = min(1.0 - 1e-9, high)
    #     if low >= high:
    #         return data
    #     try:
    #         b, a = butter(order, [low, high], btype='band')
    #         y = filtfilt(b, a, data)
    #         return y
    #     except ValueError as e:
    #         return data

    # def remove_unnecessary_subcarriers(df, channel_width='80MHz'):
    #     if df is None or df.empty:
    #         return df

    #     if channel_width not in Config.CHANNEL_CONFIGS:
    #         raise ValueError(f"Unsupported channel width: {channel_width}")

    #     subcarrier_cols = [col for col in df.columns if col.isdigit()]
    #     if not subcarrier_cols:
    #         return df

    #     if '0' in df.columns:
    #         df = df.drop(columns=['0'])
        
    #     config = Config.CHANNEL_CONFIGS[channel_width]
        
    #     for start, end in config['guard_bands']:
    #         guard_cols = [str(i) for i in range(start, end + 1) if str(i) in df.columns] # end inclusive
    #         if guard_cols:
    #             df = df.drop(columns=guard_cols)
        
    #     pilot_cols = [str(i) for i in config['pilots'] if str(i) in df.columns]
    #     if pilot_cols:
    #         df = df.drop(columns=pilot_cols)
        
    #     print(f"Removed unnecessary subcarriers for {channel_width}. Remaining: {len([col for col in df.columns if col.isdigit()])}")
    #     return df

    # def preprocess_csi_data(csi_kit_csv_path, pcap_timestamps, channel_width='80MHz'):
    #     try:
    #         print(f"Reading CSV file: {csi_kit_csv_path}")
    #         print(f"CSV file exists: {os.path.exists(csi_kit_csv_path)}")
    #         if os.path.exists(csi_kit_csv_path):
    #             print(f"CSV file size: {os.path.getsize(csi_kit_csv_path)} bytes")
            
    #         df = pd.read_csv(csi_kit_csv_path)
    #         if df.empty:
    #             print("Error: CSV file is empty")
    #             return pd.DataFrame()
    #         print(f"CSV file loaded successfully. Shape: {df.shape}")
    #         print(f"Columns: {df.columns.tolist()}")
    #     except Exception as e:
    #         print(f"Error reading CSV: {e}")
    #         return None

    #     try:
    #         print("Renaming columns...")
    #         original_columns = df.columns.tolist()
    #         df.rename(columns=lambda col: re.sub(r'^Sub\s+(-?\d+)\s+RXTX\s+0/0$', r'\1', col), inplace=True)
    #         print(f"Original columns: {original_columns}")
    #         print(f"Columns after renaming: {df.columns.tolist()}")
    #     except Exception as e:
    #         print(f"Error renaming columns: {e}")
    #         return None

    #     try:
    #         print("Removing unnecessary subcarriers...")
    #         df = remove_unnecessary_subcarriers(df, channel_width)
    #         print(f"Shape after removing subcarriers: {df.shape}")
    #         print(f"Remaining columns: {df.columns.tolist()}")
    #     except Exception as e:
    #         print(f"Error removing subcarriers: {e}")
    #         return None

    #     try:
    #         print("Converting subcarrier columns to numeric...")
    #         subcarrier_cols = [col for col in df.columns if col.lstrip('-').isdigit()]
    #         print(f"Found {len(subcarrier_cols)} subcarrier columns")
    #         for col in subcarrier_cols:
    #             df[col] = pd.to_numeric(df[col], errors='coerce')
    #         print(f"Number of subcarrier columns after conversion: {len(subcarrier_cols)}")
    #     except Exception as e:
    #         print(f"Error converting subcarrier columns: {e}")
    #         return None

    #     if not pcap_timestamps:
    #         print("Error: No PCAP timestamps provided")
    #         return None

    #     try:
    #         print("Processing timestamps...")
    #         print(f"Number of timestamps: {len(pcap_timestamps)}")
    #         print(f"DataFrame length: {len(df)}")
    #         min_len = min(len(pcap_timestamps), len(df))
    #         if min_len == 0:
    #             print("Error: No data points available")
    #             return pd.DataFrame()

    #         df = df.iloc[:min_len]
    #         df.insert(0, 'timestamp', pcap_timestamps[:min_len])
    #         print(f"Data shape after timestamp processing: {df.shape}")

    #         print("Converting timestamps to datetime...")
    #         df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp'], errors='coerce'), unit='s')
    #         print("Timestamp conversion successful")
    #     except Exception as e:
    #         print(f"Error processing timestamps: {e}")
    #         return None

    #     try:
    #         print("Dropping invalid rows...")
    #         print(f"DataFrame shape before dropping invalid rows: {df.shape}")
    #         df = drop_invalid_rows(df)
    #         print(f"Final data shape: {df.shape}")
    #         return df
    #     except Exception as e:
    #         print(f"Error dropping invalid rows: {e}")
    #         return None

    # def resample_data_by_interval(df_input, interval_sec, time_col='timestamp'):
    #     if df_input is None or df_input.empty or time_col not in df_input.columns:
    #         return pd.DataFrame()
        
    #     df = df_input.set_index(time_col)
    #     if not isinstance(df.index, pd.DatetimeIndex):
    #         return pd.DataFrame()

    #     try:
    #         resampled_df = df.resample(f'{int(interval_sec*1000)}ms').mean().reset_index()
    #     except Exception as e:
    #         return pd.DataFrame()
    #     return drop_invalid_rows(resampled_df)

    # def bandpass_filter_csv(df_input, lowcut, highcut, fs, time_col='timestamp', order=Config.FILTER_ORDER):
    #     if df_input is None or df_input.empty: return pd.DataFrame()
    #     df = df_input.copy()
    #     data_cols = [col for col in df.columns if col != time_col and pd.api.types.is_numeric_dtype(df[col])]
    #     if not data_cols: return df

    #     for col in data_cols:
    #         if contains_nan_or_inf(df[col]):
    #             continue
            
    #         if np.std(df[col]) == 0:
    #             continue
                
    #         try:
    #             df[col] = np.nan_to_num(df[col], nan=0.0, posinf=0.0, neginf=0.0)
    #             df[col] = normalize_signal(df[col])
    #             df[col] = df[col] + 1e-10
                
    #             try:
    #                 if np.all(np.isfinite(df[col])):
    #                     df[col] = detrend(df[col])
    #                 else:
    #                     print(f"Warning: Non-finite values in column {col} after normalization")
    #                     continue
    #             except Exception as e:
    #                 print(f"Warning: Detrend failed for column {col}: {e}")
    #                 continue
                    
    #             df[col] = _bandpass_filter(df[col], lowcut, highcut, fs, order)
                
    #             if contains_nan_or_inf(df[col]):
    #                 print(f"Warning: Invalid values detected in column {col} after filtering")
    #                 continue
                
    #         except Exception as e:
    #             print(f"Warning: Error processing column {col}: {e}")
    #             continue
                
    #     return drop_invalid_rows(df)

    # def apply_fourier_transform(df_input, sampling_interval, time_col='timestamp'):
    #     if df_input is None or df_input.empty: return pd.DataFrame()
    #     df = df_input.copy()
    #     data_cols = [col for col in df.columns if col != time_col and pd.api.types.is_numeric_dtype(df[col])]
    #     if not data_cols: return pd.DataFrame()

    #     all_fft_results = []
    #     for col in data_cols:
    #         signal = df[col].values
    #         if len(signal) < 2 : continue

    #         N = len(signal)
    #         yf = np.fft.fft(signal)
    #         xf = np.fft.fftfreq(N, d=sampling_interval)
            
    #         positive_mask = xf > 0
    #         xf_positive = xf[positive_mask]
    #         yf_positive_abs = np.abs(yf[positive_mask])

    #         fft_df = pd.DataFrame({'frequency': xf_positive, col: yf_positive_abs})
    #         all_fft_results.append(fft_df.set_index('frequency'))

    #     if not all_fft_results: return pd.DataFrame()
        
    #     merged_fft_df = pd.concat(all_fft_results, axis=1).reset_index()
    #     return drop_invalid_rows(merged_fft_df)

    # def average_magnitude_by_frequency_bins(df_input, bins, freq_col='frequency'):
    #     if df_input is None or df_input.empty or freq_col not in df_input.columns:
    #         return pd.DataFrame()
    #     df = df_input.copy()
    #     df['freq_interval'] = pd.cut(df[freq_col], bins=bins, right=False, include_lowest=True)
        
    #     data_cols = [col for col in df.columns if col not in [freq_col, 'freq_interval'] and pd.api.types.is_numeric_dtype(df[col])]
    #     if not data_cols: return pd.DataFrame()

    #     try:
    #         grouped_df = df.groupby('freq_interval', observed=False).mean(numeric_only=True).reset_index()
    #     except TypeError:
    #         grouped_df = df.groupby('freq_interval', observed=False)[data_cols].mean().reset_index()

    #     if 'frequency' in grouped_df.columns:
    #         grouped_df = grouped_df.drop(columns=['frequency'], errors='ignore')
    #     return grouped_df

    # def compute_cosine_similarity(file1_path, file2_path, output_path, identifier_col='freq_interval'):
    #     try:
    #         df1 = pd.read_csv(file1_path)
    #         df2 = pd.read_csv(file2_path)
    #     except Exception as e:
    #         print(f"Error reading CSV for cosine similarity: {e}")
    #         return

    #     if df1.empty or df2.empty or identifier_col not in df1.columns or identifier_col not in df2.columns:
    #         return

    #     merged_df = pd.merge(df1, df2, on=identifier_col, suffixes=('_1', '_2'), how='inner')
    #     if merged_df.empty:
    #         return
        
    #     data_cols_1 = [col for col in merged_df.columns if col.endswith('_1') and col[:-2] != identifier_col and pd.api.types.is_numeric_dtype(merged_df[col])]
    #     data_cols_2 = [col for col in merged_df.columns if col.endswith('_2') and col[:-2] != identifier_col and pd.api.types.is_numeric_dtype(merged_df[col])]

    #     if not data_cols_1 or not data_cols_2 or len(data_cols_1) != len(data_cols_2):
    #         return

    #     vec1 = merged_df[data_cols_1].values.T
    #     vec2 = merged_df[data_cols_2].values.T

    #     if vec1.shape[1] == 0 or vec2.shape[1] == 0 :
    #         return

    #     avg_vec1 = np.mean(vec1, axis=0) if vec1.ndim > 1 else vec1.flatten()
    #     avg_vec2 = np.mean(vec2, axis=0) if vec2.ndim > 1 else vec2.flatten()

    #     if avg_vec1.ndim == 0 : avg_vec1 = avg_vec1.reshape(1, -1)
    #     if avg_vec2.ndim == 0 : avg_vec2 = avg_vec2.reshape(1, -1)
    #     if avg_vec1.shape[0] == 1 and avg_vec1.shape[1] > 1:
    #         pass
    #     elif avg_vec1.shape[1] == 1 and avg_vec1.shape[0] > 1:
    #         avg_vec1 = avg_vec1.T
    #         avg_vec2 = avg_vec2.T
    #     elif avg_vec1.size == 0 or avg_vec2.size == 0:
    #         print("Empty vectors after averaging, cannot compute similarity.")
    #         return

    #     try:
    #         similarity = cosine_similarity(avg_vec1.reshape(1, -1), avg_vec2.reshape(1, -1))[0, 0]
    #         pd.DataFrame([{'similarity': similarity}]).to_csv(output_path, index=False)
    #         print(f"Cosine similarity: {similarity:.4f} -> saved to {output_path}")
    #     except ValueError as e:
    #         print(f"Error computing cosine similarity (possibly due to zero vectors): {e}")

    # def plot_time_series_from_dataframe(df, output_path, title_suffix='', time_col='timestamp'):
    #     if df is None or df.empty or time_col not in df.columns: return
    #     data_cols = [col for col in df.columns if col != time_col and pd.api.types.is_numeric_dtype(df[col])]
    #     if not data_cols: return

    #     plt.figure(figsize=Config.PLOT_FIGSIZE)
        
    #     for i, col in enumerate(data_cols):
    #         color = Config.PLOT_COLORS[i % len(Config.PLOT_COLORS)]
    #         plt.plot(df[time_col], df[col], color=color, linewidth=Config.PLOT_LINE_WIDTH)
        
    #     plt.xlabel("Time")
    #     plt.ylabel("Amplitude")
    #     plt.title(f"Time Series {title_suffix}")
    #     plt.grid(True, alpha=Config.PLOT_GRID_ALPHA)
    #     plt.xticks(rotation=45)
        
    #     plt.tight_layout()
    #     plt.savefig(output_path, dpi=300, bbox_inches='tight')
    #     plt.close()
    #     print(f"Time series plot saved to {output_path}")

    # def plot_fft_from_dataframe(df, output_path, title_suffix='', freq_col='frequency'):
    #     if df is None or df.empty or freq_col not in df.columns:
    #         return

    #     data_cols = [col for col in df.columns if col != freq_col and col != 'freq_interval' and pd.api.types.is_numeric_dtype(df[col])]
    #     if not data_cols:
    #         return

    #     avg_spectrum = df[data_cols].mean(axis=1)
        
    #     threshold = np.max(avg_spectrum) * 0.01
    #     significant_mask = avg_spectrum > threshold
    #     if significant_mask.any():
    #         cutoff_freq = df[freq_col][significant_mask].iloc[-1]
    #     else:
    #         cutoff_freq = df[freq_col].iloc[-1] if not df[freq_col].empty else 0 # Handle empty case

    #     plt.figure(figsize=Config.PLOT_FIGSIZE)
        
    #     mask = df[freq_col] <= cutoff_freq
    #     plt.plot(df[freq_col][mask], avg_spectrum[mask], 
    #             color=Config.PLOT_COLORS[0], 
    #             linewidth=Config.PLOT_LINE_WIDTH)
        
    #     plt.xlabel("Frequency (Hz)")
    #     plt.ylabel("Magnitude")
    #     plt.title(f"FFT Spectrum {title_suffix}")
    #     plt.grid(True, alpha=Config.PLOT_GRID_ALPHA)
    #     plt.xticks(rotation=45)
        
    #     plt.tight_layout()
    #     plt.savefig(output_path, dpi=300, bbox_inches='tight')
    #     plt.close()

    # def select_best_subcarriers(fft_df, freq_col='frequency', freq_min=None, freq_max=None):
    #     if fft_df is None or fft_df.empty or freq_col not in fft_df.columns:
    #         return []

    #     data_cols = [col for col in fft_df.columns if col != freq_col and pd.api.types.is_numeric_dtype(fft_df[col])] # check dtype
    #     if not data_cols:
    #         return []

    #     if freq_min is None:
    #         freq_min = Config.BREATHING_MIN_FREQ
    #     if freq_max is None:
    #         freq_max = Config.BREATHING_MAX_FREQ

    #     mask = (fft_df[freq_col] >= freq_min) & (fft_df[freq_col] <= freq_max)
    #     target_range = fft_df[mask]

    #     snr_scores = {}
    #     for col in data_cols:
    #         if not pd.api.types.is_numeric_dtype(target_range[col]) or not pd.api.types.is_numeric_dtype(fft_df[~mask][col]):
    #             continue # Skip non-numeric columns that might have slipped through
    #         target_power = np.mean(target_range[col] ** 2)
    #         noise_power = np.mean(fft_df[~mask][col] ** 2) # ensure column exists and is numeric
    #         if noise_power > 0: # and not np.isnan(target_power) and not np.isnan(noise_power):
    #             if not (np.isnan(target_power) or np.isnan(noise_power)): # Check for NaNs
    #                 snr_scores[col] = target_power / noise_power

    #     selected_cols = sorted(snr_scores.items(), key=lambda x: x[1], reverse=True)
    #     selected_cols = [col for col, _ in selected_cols[:Config.TOP_SUBCARRIERS]]
    #     return selected_cols

    # def extract_breathing_rate(fft_df, freq_col='frequency'):
    #     if fft_df is None or fft_df.empty or freq_col not in fft_df.columns:
    #         return None, []

    #     selected_cols = select_best_subcarriers(fft_df, freq_col, 
    #                                             Config.BREATHING_MIN_FREQ, 
    #                                             Config.BREATHING_MAX_FREQ)
    #     if not selected_cols:
    #         return None, []

    #     avg_spectrum = fft_df[selected_cols].mean(axis=1)
    #     mask = (fft_df[freq_col] >= Config.BREATHING_MIN_FREQ) & (fft_df[freq_col] <= Config.BREATHING_MAX_FREQ)
        
    #     if not mask.any(): return None, selected_cols

    #     breathing_range = avg_spectrum[mask]
    #     breathing_freqs = fft_df[freq_col][mask]
        
    #     if len(breathing_range) == 0:
    #         return None, selected_cols

    #     peaks, _ = find_peaks(breathing_range, prominence=Config.PEAK_PROMINENCE)
        
    #     if len(peaks) == 0:
    #         return None, selected_cols

    #     peak_freqs = breathing_freqs.iloc[peaks]
    #     peak_heights = breathing_range.iloc[peaks]
    #     dominant_peak_idx = peak_heights.argmax()
    #     breathing_freq = peak_freqs.iloc[dominant_peak_idx]
    #     breathing_rate = breathing_freq * 60
        
    #     return breathing_rate, selected_cols

    # def extract_heart_rate(fft_df, freq_col='frequency'):
    #     if fft_df is None or fft_df.empty or freq_col not in fft_df.columns:
    #         return None, []

    #     selected_cols = select_best_subcarriers(fft_df, freq_col,
    #                                             Config.HEART_MIN_FREQ,
    #                                             Config.HEART_MAX_FREQ)
    #     if not selected_cols:
    #         return None, []

    #     avg_spectrum = fft_df[selected_cols].mean(axis=1)
    #     mask = (fft_df[freq_col] >= Config.HEART_MIN_FREQ) & (fft_df[freq_col] <= Config.HEART_MAX_FREQ)

    #     if not mask.any(): return None, selected_cols
    #     heart_range = avg_spectrum[mask]
    #     heart_freqs = fft_df[freq_col][mask]
        
    #     if len(heart_range) == 0:
    #         return None, selected_cols

    #     peaks, _ = find_peaks(heart_range, prominence=Config.HEART_PEAK_PROMINENCE)
        
    #     if len(peaks) == 0:
    #         return None, selected_cols

    #     peak_freqs = heart_freqs.iloc[peaks]
    #     peak_heights = heart_range.iloc[peaks]
    #     dominant_peak_idx = peak_heights.argmax()
    #     heart_freq = peak_freqs.iloc[dominant_peak_idx]
    #     heart_rate = heart_freq * 60
        
    #     return heart_rate, selected_cols

    # def plot_breathing_spectrum(fft_df, breathing_rate, selected_cols, output_path, freq_col='frequency'):
    #     if fft_df is None or fft_df.empty or freq_col not in fft_df.columns or not selected_cols:
    #         return

    #     avg_spectrum = fft_df[selected_cols].mean(axis=1)
        
    #     threshold = np.max(avg_spectrum) * 0.01
    #     significant_mask = avg_spectrum > threshold
    #     if significant_mask.any():
    #         cutoff_freq = fft_df[freq_col][significant_mask].iloc[-1]
    #     else:
    #         cutoff_freq = fft_df[freq_col].iloc[-1] if not fft_df[freq_col].empty else 0
        
    #     mask = fft_df[freq_col] <= cutoff_freq
        
    #     plt.figure(figsize=Config.PLOT_FIGSIZE)
    #     plt.plot(fft_df[freq_col][mask], avg_spectrum[mask], 
    #             color=Config.PLOT_COLORS[0], 
    #             linewidth=Config.PLOT_LINE_WIDTH)
        
    #     breathing_mask = (fft_df[freq_col][mask] >= Config.BREATHING_MIN_FREQ) & (fft_df[freq_col][mask] <= Config.BREATHING_MAX_FREQ)
    #     plt.axvspan(Config.BREATHING_MIN_FREQ, Config.BREATHING_MAX_FREQ, 
    #                 alpha=0.2, color='green', label='Breathing Range')
        
    #     if breathing_rate is not None:
    #         breathing_freq = breathing_rate / 60
    #         plt.axvline(x=breathing_freq, color='red', linestyle='--',
    #                 label=f'Breathing Rate: {breathing_rate:.1f} bpm')
        
    #     plt.xlabel('Frequency (Hz)')
    #     plt.ylabel('Magnitude')
    #     plt.title('FFT Spectrum with Breathing Rate')
    #     plt.grid(True, alpha=Config.PLOT_GRID_ALPHA)
    #     plt.legend()
    #     plt.tight_layout()
    #     plt.savefig(output_path, dpi=300, bbox_inches='tight')
    #     plt.close()

    # def plot_vital_signs_spectrum(fft_df, breathing_rate, heart_rate, breathing_cols, heart_cols, output_path, freq_col='frequency'):
    #     if fft_df is None or fft_df.empty or freq_col not in fft_df.columns:
    #         return

    #     plt.figure(figsize=Config.PLOT_FIGSIZE)
        
    #     # Calculate cutoff frequency based on significant values
    #     if breathing_cols and all(col in fft_df.columns for col in breathing_cols):
    #         breathing_spectrum = fft_df[breathing_cols].mean(axis=1)
    #         if not np.all(np.abs(np.diff(breathing_spectrum)) <= 1e-10):
    #             threshold = np.max(breathing_spectrum) * 0.01
    #             significant_mask = breathing_spectrum > threshold
    #             if significant_mask.any():
    #                 cutoff_freq = fft_df[freq_col][significant_mask].iloc[-1]
    #             else:
    #                 cutoff_freq = fft_df[freq_col].iloc[-1] if not fft_df[freq_col].empty else 0
                
    #             mask = fft_df[freq_col] <= cutoff_freq
    #             plt.plot(fft_df[freq_col][mask], breathing_spectrum[mask], 
    #                     color='green', alpha=0.5, label='Breathing Spectrum')
        
    #     if heart_cols and all(col in fft_df.columns for col in heart_cols):
    #         heart_spectrum = fft_df[heart_cols].mean(axis=1)
    #         if not np.all(np.abs(np.diff(heart_spectrum)) <= 1e-10):
    #             threshold = np.max(heart_spectrum) * 0.01
    #             significant_mask = heart_spectrum > threshold
    #             if significant_mask.any():
    #                 cutoff_freq = fft_df[freq_col][significant_mask].iloc[-1]
    #             else:
    #                 cutoff_freq = fft_df[freq_col].iloc[-1] if not fft_df[freq_col].empty else 0
                
    #             mask = fft_df[freq_col] <= cutoff_freq
    #             plt.plot(fft_df[freq_col][mask], heart_spectrum[mask], 
    #                     color='red', alpha=0.5, label='Heart Rate Spectrum')
        
    #     # Only show ranges if there is non-constant data
    #     if (breathing_cols and not np.all(np.abs(np.diff(fft_df[breathing_cols].mean(axis=1))) <= 1e-10)) or \
    #     (heart_cols and not np.all(np.abs(np.diff(fft_df[heart_cols].mean(axis=1))) <= 1e-10)):
    #         plt.axvspan(Config.BREATHING_MIN_FREQ, Config.BREATHING_MAX_FREQ, 
    #                     alpha=0.2, color='green', label='Breathing Range')
    #         plt.axvspan(Config.HEART_MIN_FREQ, Config.HEART_MAX_FREQ, 
    #                     alpha=0.2, color='red', label='Heart Rate Range')
        
    #     if breathing_rate is not None:
    #         breathing_freq = breathing_rate / 60
    #         plt.axvline(x=breathing_freq, color='green', linestyle='--', label=f'Breathing Rate: {breathing_rate:.1f} bpm')
        
    #     if heart_rate is not None:
    #         heart_freq = heart_rate / 60
    #         plt.axvline(x=heart_freq, color='red', linestyle='--', label=f'Heart Rate: {heart_rate:.1f} bpm')
        
    #     plt.xlabel('Frequency (Hz)')
    #     plt.ylabel('Magnitude')
    #     plt.title('FFT Spectrum with Vital Signs')
    #     plt.grid(True, alpha=Config.PLOT_GRID_ALPHA)
    #     plt.legend()
    #     plt.tight_layout()
    #     plt.savefig(output_path, dpi=300, bbox_inches='tight')
    #     plt.close()

    # def compute_subcarrier_changes(current_df, baseline_df):
    #     """
    #     現在のCSIデータとベースラインCSIデータを比較し、変化の大きいサブキャリアを特定
    #     フーリエ変換後の周波数領域での変化を比較
        
    #     Args:
    #         current_df: 現在のCSIデータのDataFrame
    #         baseline_df: ベースラインCSIデータのDataFrame
        
    #     Returns:
    #         list: 変化の大きいサブキャリアのリスト
    #     """
    #     if current_df is None or baseline_df is None or current_df.empty or baseline_df.empty:
    #         return []
        
    #     # サブキャリア列を取得
    #     subcarrier_cols = [col for col in current_df.columns if col.lstrip('-').isdigit()]
        
    #     # 各サブキャリアのフーリエ変換を計算
    #     current_fft = apply_fourier_transform(current_df, Config.DOWNSAMPLE_INTERVAL_S)
    #     baseline_fft = apply_fourier_transform(baseline_df, Config.DOWNSAMPLE_INTERVAL_S)
        
    #     if current_fft is None or baseline_fft is None or current_fft.empty or baseline_fft.empty:
    #         return []
        
    #     # 呼吸と心拍の周波数帯域を定義
    #     breathing_range = (Config.BREATHING_MIN_FREQ, Config.BREATHING_MAX_FREQ)
    #     heart_range = (Config.HEART_MIN_FREQ, Config.HEART_MAX_FREQ)
        
    #     # 各サブキャリアの変化量を計算
    #     changes = {}
    #     for col in subcarrier_cols:
    #         if col in current_fft.columns and col in baseline_fft.columns:
    #             # 呼吸周波数帯域での変化
    #             breathing_mask = (current_fft['frequency'] >= breathing_range[0]) & \
    #                         (current_fft['frequency'] <= breathing_range[1])
    #             breathing_current = current_fft.loc[breathing_mask, col]
    #             breathing_baseline = baseline_fft.loc[breathing_mask, col]
                
    #             # 心拍周波数帯域での変化
    #             heart_mask = (current_fft['frequency'] >= heart_range[0]) & \
    #                         (current_fft['frequency'] <= heart_range[1])
    #             heart_current = current_fft.loc[heart_mask, col]
    #             heart_baseline = baseline_fft.loc[heart_mask, col]
                
    #             # 各周波数帯域での変化量を計算
    #             breathing_change = np.mean(np.abs(breathing_current - breathing_baseline))
    #             heart_change = np.mean(np.abs(heart_current - heart_baseline))
                
    #             # ベースラインの振幅で正規化
    #             breathing_baseline_amp = np.mean(np.abs(breathing_baseline))
    #             heart_baseline_amp = np.mean(np.abs(heart_baseline))
                
    #             if breathing_baseline_amp > 0 and heart_baseline_amp > 0:
    #                 normalized_breathing_change = breathing_change / breathing_baseline_amp
    #                 normalized_heart_change = heart_change / heart_baseline_amp
                    
    #                 # 呼吸と心拍の変化を重み付けして合計
    #                 total_change = (normalized_breathing_change * 0.6 + normalized_heart_change * 0.4)
    #                 changes[col] = total_change
        
    #     # 変化量でソートし、上位のサブキャリアを選択
    #     sorted_changes = sorted(changes.items(), key=lambda x: x[1], reverse=True)
    #     selected_subcarriers = [col for col, _ in sorted_changes[:Config.TOP_SUBCARRIERS]]
        
    #     return selected_subcarriers

    # def load_latest_baseline_data(baseline_dir):
    #     """
    #     ベースCSIデータのウィンドウを読み込む関数
        
    #     Args:
    #         baseline_dir (str): ベースCSIデータのディレクトリ
        
    #     Returns:
    #         list: ベースCSIデータのウィンドウのリスト
    #     """
    #     if not os.path.exists(baseline_dir):
    #         raise FileNotFoundError(f"ベースCSIデータディレクトリが見つかりません: {baseline_dir}")
        
    #     # ウィンドウファイルを読み込む
    #     window_files = sorted([f for f in os.listdir(baseline_dir) if f.startswith('window_') and f.endswith('.csv')])
    #     if not window_files:
    #         raise FileNotFoundError(f"ベースCSIデータのウィンドウファイルが見つかりません: {baseline_dir}")
        
    #     baseline_windows = []
    #     for window_file in window_files:
    #         window_path = os.path.join(baseline_dir, window_file)
    #         try:
    #             df = pd.read_csv(window_path)
    #             baseline_windows.append(df)
    #         except Exception as e:
    #             print(f"警告: ウィンドウファイルの読み込みに失敗しました {window_file}: {e}")
    #             continue
        
    #     return baseline_windows

    # def process_pipeline(df, output_dir, input_base, baseline_dir=None):
    #     """
    #     CSIデータの処理パイプライン
        
    #     Args:
    #         df (pd.DataFrame): 処理するCSIデータ
    #         output_dir (str): 出力ディレクトリ
    #         input_base (str): 入力ファイルのベース名
    #         baseline_dir (str, optional): ベースCSIデータのディレクトリ
    #     """
    #     try:
    #         # 初期データの保存
    #         save_initial_data(df, output_dir, input_base)
            
    #         # データの前処理
    #         df = drop_invalid_rows(df)
    #         if df.empty:
    #             raise ValueError("有効なデータがありません")
            
    #         # サブキャリアの正規化
    #         subcarrier_cols = [col for col in df.columns if col.lstrip('-').isdigit()]
    #         for col in subcarrier_cols:
    #             df[col] = normalize_signal(df[col])
            
    #         # バンドパスフィルタの適用
    #         fs = 1.0 / Config.DOWNSAMPLE_INTERVAL_S
    #         df = bandpass_filter_csv(df, Config.BANDPASS_LOWCUT, Config.BANDPASS_HIGHCUT, fs)
            
    #         # フーリエ変換の適用
    #         fft_df = apply_fourier_transform(df, Config.DOWNSAMPLE_INTERVAL_S)
            
    #         # 呼吸数と心拍数の抽出
    #         breathing_rate = extract_breathing_rate(fft_df)
    #         heart_rate = extract_heart_rate(fft_df)
            
    #         # 最適なサブキャリアの選択
    #         breathing_cols = select_best_subcarriers(fft_df, 
    #                                             freq_min=Config.BREATHING_MIN_FREQ,
    #                                             freq_max=Config.BREATHING_MAX_FREQ)
    #         heart_cols = select_best_subcarriers(fft_df,
    #                                         freq_min=Config.HEART_MIN_FREQ,
    #                                         freq_max=Config.HEART_MAX_FREQ)
            
    #         # ベースCSIデータとの比較
    #         if baseline_dir:
    #             try:
    #                 baseline_windows = load_latest_baseline_data(baseline_dir)
    #                 if baseline_windows:
    #                     # 各ベースウィンドウとの類似度を計算
    #                     similarities = []
    #                     for baseline_df in baseline_windows:
    #                         similarity = compute_cosine_similarity(
    #                             df[breathing_cols].values,
    #                             baseline_df[breathing_cols].values
    #                         )
    #                         similarities.append(similarity)
                        
    #                     # 類似度の平均を計算
    #                     avg_similarity = np.mean(similarities)
    #                     print(f"ベースCSIデータとの平均類似度: {avg_similarity:.3f}")
                        
    #                     # 類似度が低い場合は警告
    #                     if avg_similarity < 0.7:
    #                         print("警告: ベースCSIデータとの類似度が低いです")
    #             except Exception as e:
    #                 print(f"警告: ベースCSIデータとの比較に失敗しました: {e}")
            
    #         # 結果のプロット
    #         plot_breathing_spectrum(fft_df, breathing_rate, breathing_cols, 
    #                             os.path.join(output_dir, f"{os.path.basename(input_base)}_breathing.png"))
    #         plot_vital_signs_spectrum(fft_df, breathing_rate, heart_rate,
    #                                 breathing_cols, heart_cols,
    #                                 os.path.join(output_dir, f"{os.path.basename(input_base)}_vital_signs.png"))
            
    #         # 結果の保存
    #         results = {
    #             'breathing_rate': breathing_rate,
    #             'heart_rate': heart_rate,
    #             'breathing_subcarriers': breathing_cols,
    #             'heart_subcarriers': heart_cols
    #         }
            
    #         if baseline_dir and 'avg_similarity' in locals():
    #             results['baseline_similarity'] = avg_similarity
            
    #         # 結果をJSONファイルとして保存
    #         import json
    #         results_file = os.path.join(output_dir, f"{os.path.basename(input_base)}_results.json")
    #         with open(results_file, 'w') as f:
    #             json.dump(results, f, indent=4)
            
    #         print(f"解析結果を保存しました: {results_file}")
            
    #     except Exception as e:
    #         print(f"エラー: データ処理中にエラーが発生しました: {e}")
    #         raise

# サービスインスタンス
pcap_analyzer = PCAPAnalyzer()