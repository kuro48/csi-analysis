export type CSIStatus = "uploaded" | "processing" | "completed" | "error";

export type DataframeDict = {
  frequency?: Record<string, number | null>;
  magnitude_avg?: Record<string, number | null>;
} | null;

export type SignalDict = {
  start_timestamp?: string | null;
  time?: Record<string, number | null>;
  amplitude_avg?: Record<string, number | null>;
} | null;

export interface SignalPoint {
  /** 開始からの経過秒 */
  time: number;
  /** エポックミリ秒（start_timestamp がある場合のみ設定） */
  ts?: number;
  amplitude: number;
}

export interface BaseCSIResponse {
  id: string;
  name: string;
  fft_dataframe: DataframeDict;
  wavelet_dataframe: DataframeDict;
  music_dataframe: DataframeDict;
  raw_signal_dataframe?: SignalDict;
  filtered_signal_dataframe?: SignalDict;
  source_pcap_size: number | null;
  status: CSIStatus;
  error_message: string | null;
  is_expired: boolean;
  created_at: string;
  updated_at: string;
}

export interface MethodComparison {
  similarity_score: number;
  is_valid: boolean;
  python_similarity?: number | null;
  selected_subcarrier?: {
    index: number | null;
    similarity: number | null;
  };
  data_dimensions?: {
    num_freq_points: number;
    num_subcarriers: number;
    total_dimensions: number;
  };
}

export interface BaseCSIComparison {
  base_csi_id: string;
  base_csi_name: string;
  similarity_score: number;
  methods: Partial<Record<"fft" | "wavelet" | "music", MethodComparison>>;
  primary_method?: "fft" | "wavelet" | "music";
  is_valid?: boolean;
  selected_subcarrier?: {
    index: number | null;
    similarity: number | null;
  };
  data_dimensions?: {
    num_freq_points: number;
    num_subcarriers: number;
    total_dimensions: number;
  };
  comparison_summary?: {
    generated_methods: string[];
    primary_method: string;
    similarity_delta: number | null;
  };
}

export interface BreathingRateComparison {
  final_bpm?: number | null;
  preferred_method?: string | null;
  fft_bpm?: number | null;
  wavelet_bpm?: number | null;
  music_bpm?: number | null;
  methods?: Record<string, number | null>;
}

export interface ProcessedData {
  fft_dataframe?: DataframeDict;
  wavelet_dataframe?: DataframeDict;
  music_dataframe?: DataframeDict;
  raw_signal?: SignalDict;
  filtered_signal?: SignalDict;
  breathing_rate_comparison?: BreathingRateComparison;
  fft_phase_dataframe?: DataframeDict;
  wavelet_phase_dataframe?: DataframeDict;
  music_phase_dataframe?: DataframeDict;
  breathing_rate_phase_comparison?: BreathingRateComparison;
  base_csi_comparison?: BaseCSIComparison;
  wavelet_zkp?: TransformZKPResult | null;
  music_zkp?: TransformZKPResult | null;
  blockchain_proof_id?: string;
  blockchain_proof_data?: Record<string, unknown>;
  error?: string;
}

export interface MainCSIResponse {
  id: string;
  session_id: string | null;
  device_id: string | null;
  raw_data?: Record<string, unknown> | Array<Record<string, unknown>> | null;
  file_path?: string | null;
  file_size: number | null;
  status: CSIStatus;
  processed_data: ProcessedData | null;
  created_at: string;
  updated_at: string;
}

export interface CSIDataListResponse {
  csi_data: MainCSIResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TransformZKPResult {
  is_normal: boolean;
  proof_id: string | null;
}

export interface SpectrumPoint {
  frequency: number;
  magnitude: number;
}
