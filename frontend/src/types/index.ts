/**
 * 型定義ファイル
 */

// ユーザー関連
export interface User {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string;
}

// デバイス関連
export interface Device {
  id: string;
  device_id: string;
  device_name: string;
  device_type: string;
  location?: string;
  owner_id?: string;
  is_active: boolean;
  last_seen?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateDeviceRequest {
  device_id: string;
  device_name: string;
  device_type: string;
  location?: string;
}

export interface DeviceHeartbeat {
  status: 'online' | 'offline' | 'busy';
  cpu_usage?: number;
  memory_usage?: number;
  disk_usage?: number;
  temperature?: number;
  uptime?: number;
}

// CSIデータ関連
export interface CSIRawData {
  subcarriers: number[];
  timestamps: number[];
  amplitudes: number[][];
  phases: number[][];
}

export interface CSIProcessedData {
  filtered_amplitudes?: number[][];
  breathing_signal?: number[];
  frequency_peaks?: number[];
  quality_score?: number;
}

export interface CSIData {
  id: string;
  device_id: string;
  session_id?: string;
  raw_data?: CSIRawData;
  processed_data?: CSIProcessedData;
  file_path?: string;
  file_size?: number;
  status: 'received' | 'processing' | 'processed' | 'error';
  created_at: string;
}

export interface CSIDataListResponse {
  csi_data: CSIData[];
  total: number;
  page: number;
  page_size: number;
}

export interface CSIStats {
  total_samples: number;
  avg_quality: number;
  date_range: {
    start: string;
    end: string;
  };
  status_distribution: {
    received: number;
    processing: number;
    processed: number;
    error: number;
  };
}

export interface CSIVisualizationData {
  timestamps: number[];
  amplitudes: number[][];
  phases: number[][];
  subcarrier_indices: number[];
  metadata: {
    device_id: string;
    sample_rate: number;
    total_samples: number;
  };
}

// 呼吸解析結果関連
export interface FrequencyDomainData {
  frequencies: number[];
  power_spectrum: number[];
  dominant_frequency?: number;
  snr?: number;
}

export interface TimeDomainData {
  timestamps: number[];
  breathing_signal: number[];
  peaks: number[];
  valleys: number[];
}

export interface QualityMetrics {
  signal_quality: number;
  noise_level: number;
  confidence: number;
  data_completeness: number;
}

export interface BreathingAnalysis {
  id: string;
  csi_data_id: string;
  device_id: string;
  breathing_rate?: number;
  confidence_score?: number;
  analysis_timestamp: string;
  window_start?: string;
  window_end?: string;
  frequency_domain_data?: FrequencyDomainData;
  time_domain_data?: TimeDomainData;
  quality_metrics?: QualityMetrics;
  ipfs_hash?: string;
  blockchain_tx_hash?: string;
  created_at: string;
}

export interface BreathingAnalysisListResponse {
  analyses: BreathingAnalysis[];
  total: number;
  page: number;
  page_size: number;
}

export interface BreathingTrend {
  timestamp: string;
  breathing_rate: number;
  confidence_score: number;
  quality: number;
}

// セッション関連
export interface SessionMetadata {
  purpose?: string;
  location?: string;
  notes?: string;
  participant_count?: number;
  environment?: string;
}

export interface Session {
  id: string;
  device_id: string;
  session_name?: string;
  start_time: string;
  end_time?: string;
  duration?: number;
  status: 'active' | 'completed' | 'stopped' | 'error';
  metadata?: SessionMetadata;
  created_at: string;
}

// アラート関連
export interface Alert {
  id: string;
  device_id: string;
  alert_type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  message?: string;
  is_acknowledged: boolean;
  acknowledged_by?: string;
  acknowledged_at?: string;
  created_at: string;
}

// API レスポンス型
export interface ApiResponse<T> {
  data: T;
  message?: string;
  status: 'success' | 'error';
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

// 認証関連
export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// ナビゲーション関連
export interface NavItem {
  title: string;
  href: string;
  icon?: string;
  disabled?: boolean;
  external?: boolean;
  children?: NavItem[];
}

// チャート・可視化関連
export interface ChartDataPoint {
  timestamp: string;
  value: number;
  label?: string;
}

export interface BreathingRateChart {
  data: ChartDataPoint[];
  device_id: string;
  time_range: string;
}