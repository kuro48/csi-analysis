export type CSIStatus = "uploaded" | "processing" | "completed" | "error";

export interface SignalPoint {
  /** 開始からの経過秒 */
  time: number;
  /** エポックミリ秒（start_timestamp がある場合のみ設定） */
  ts?: number;
  amplitude: number;
}

export interface VMDModeSummary {
  mode: number;
  global_peak_freq_hz: number;
  global_peak_bpm: number;
  global_peak_ratio: number;
  is_valid: boolean;
}

export interface CertificateDiagnostics {
  recon_error_ratio?: number;
  recon_error_ratio_threshold?: number;
  recon_ok?: boolean;
  narrow_ratio?: number;
  narrow_ratio_threshold?: number;
  narrow_ok?: boolean;
  max_mode_abs?: number;
  mode_max_abs_limit?: number;
  scale_factor?: number;
}

export interface LombScargleAnalysis {
  status: "completed" | "failed";
  algorithm_version?: string;
  breathing_rate_bpm?: number;
  peak_freq_hz?: number;
  peak_power?: number;
  global_peak_bpm?: number;
  global_peak_freq_hz?: number;
  selected_pc?: number;
  pc_explained_variance_ratio?: number[];
  pc_target_peak_powers?: number[];
  selected_pc_waveform?: number[];
  n_samples?: number;
  n_subcarriers_total?: number;
  n_subcarriers_selected?: number;
  duration_seconds?: number;
  actual_sampling_rate_hz?: number;
  sampling_interval_cv?: number;
  duplicates_removed?: number;
  processing_time_seconds?: number;
  processing_steps?: ProcessingStepTiming[];
  normality_rule?: string;
  circom_scope?: string;
  error?: string;
  error_type?: string;
}

export interface ProcessingStepTiming {
  key: string;
  label: string;
  seconds: number;
}

export interface AlgorithmComparison {
  current_algorithm?: string;
  lomb_scargle_algorithm?: string;
  current_breathing_rate_bpm?: number;
  lomb_scargle_breathing_rate_bpm?: number;
  absolute_difference_bpm?: number;
  current_is_normal?: boolean;
  lomb_scargle_is_normal?: boolean;
}

export interface BpmEvaluationRow {
  method: "5-1" | "lomb_scargle";

  method_label: string;
  ground_truth_bpm: number;
  measured_bpm: number | null;
  signed_error_bpm: number | null;
  absolute_error_bpm: number | null;
}

export interface BpmEvaluation {
  ground_truth_bpm: number;
  rows: BpmEvaluationRow[];
}

export interface BreathingAnalysis {
  pipeline?: string;
  respiration_waveform?: number[];
  breathing_rate_bpm?: number;
  peak_freq_hz?: number;
  selected_pc?: number;
  pc_scores?: number[];
  selected_vmd_mode?: number;
  vmd_mode_summaries?: VMDModeSummary[];
  n_samples?: number;
  n_subcarriers_total?: number;
  n_subcarriers_selected?: number;
  bpm_range?: {
    min: number;
    max: number;
  };
  processing_time_seconds?: number;
  certificate_diagnostics?: CertificateDiagnostics;
  lomb_scargle?: LombScargleAnalysis;
  algorithm_comparison?: AlgorithmComparison;
}

export interface ProcessedData {
  status?: "completed" | "partial" | "failed";
  analysis?: BreathingAnalysis;
  proofs?: {
    python_circom?: VerifiableProofResult;
    lomb_scargle_circom?: VerifiableProofResult;

  };
  bpm_evaluation?: BpmEvaluation;
  disabled_methods?: string[];
  error?: string;
}

export interface ProofPerformance {
  circuit_name?: string;
  proof_system?: string;
  constraint_count?: number;
  wire_count?: number;
  public_output_count?: number;
  public_input_count?: number;
  private_input_count?: number;
  label_count?: number;
  witness_time_seconds?: number;
  prove_time_seconds?: number;
  generation_time_seconds?: number;
  verify_time_seconds?: number;
}

export interface VerifiableProofResult {
  status: "completed" | "failed";
  isNormal?: boolean;
  isValid?: boolean;
  method?: string;
  proofScope?: string;
  estimatedFrequencyHz?: number;
  estimatedBpm?: number;
  globalPeakFrequencyHz?: number;
  globalPeakBpm?: number;
  error?: string;
  error_type?: string;
  reason?: string;
  performance?: ProofPerformance;
  benchmark?: CircomProofBenchmark;
}

export interface CircomProofBenchmark {
  circuitName: string;
  provingSystem: "groth16" | string;
  curve: string;
  constraintCount: number | null;
  witnessGenerationMs: number;
  proofGenerationMs: number;
  verificationMs: number | null;
  totalMs: number;
  averageProofTimePerConstraintNs: number | null;
  measuredAt: string;
  stageBreakdown: ProofStageBreakdown | null;
}

export interface ProofStageTiming {
  key: string;
  label: string;
  description: string | null;
  constraints: number;
  constraintShare: number;
  estimatedMs: number;
}

/** Groth16は全制約を一括証明するため、段階別の値は実測総時間を制約数比で按分したもの。 */
export interface ProofStageBreakdown {
  stages: ProofStageTiming[];
  fixedOverheadMs: number;
  attributedWorkMs: number;
  totalConstraints: number;
  profileMeasuredAt: string | null;
  method: string;
}

export interface MainCSIResponse {
  id: string;
  session_id: string | null;
  device_id: string | null;
  ground_truth_bpm?: number | null;
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

