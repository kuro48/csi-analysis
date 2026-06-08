export type CSIStatus = "uploaded" | "processing" | "completed" | "error";

export type DataframeDict = {
  frequency?: Record<string, number | null>;
  magnitude_avg?: Record<string, number | null>;
} | null;

export interface BaseCSIResponse {
  id: string;
  name: string;
  fft_dataframe: DataframeDict;
  wavelet_dataframe: DataframeDict;
  music_dataframe: DataframeDict;
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
}

export interface BaseCSIComparison {
  base_csi_id: string;
  base_csi_name: string;
  similarity_score: number;
  methods: Partial<Record<"fft" | "wavelet" | "music", MethodComparison>>;
}

export interface BreathingRateComparison {
  final_bpm: number | null;
  methods: Record<string, number | null>;
}

export interface ProcessedData {
  fft_dataframe?: DataframeDict;
  wavelet_dataframe?: DataframeDict;
  music_dataframe?: DataframeDict;
  breathing_rate_comparison?: BreathingRateComparison;
  base_csi_comparison?: BaseCSIComparison;
  error?: string;
}

export interface MainCSIResponse {
  id: string;
  status: CSIStatus;
  processed_data: ProcessedData | null;
  created_at: string;
  updated_at: string;
}

export interface SpectrumPoint {
  frequency: number;
  magnitude: number;
}
