#![cfg_attr(not(feature = "std"), no_std)]

extern crate alloc;

use alloc::{string::String, vec, vec::Vec};
use core::cmp::Ordering;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const MAX_SELECTED_SUBCARRIERS: usize = 32;
pub const PCA_ITERATIONS: usize = 8;
pub const VMD_MODES: usize = 5;
pub const VMD_ITERATIONS: usize = 12;
pub const ALGORITHM_VERSION: &str = "5-1-fixed-v1";

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct PipelineInput {
    pub samples: usize,
    pub subcarriers: usize,
    pub amplitudes: Vec<i32>,
    pub scale: u32,
    pub sample_rate_hz: u32,
    pub bpm_min: u32,
    pub bpm_max: u32,
    pub input_commitment: String,
    pub algorithm_version: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct PipelineJournal {
    pub algorithm_version: String,
    pub input_commitment: String,
    pub breathing_rate_milli_bpm: u32,
    pub peak_frequency_micro_hz: u32,
    pub is_normal: bool,
    pub selected_pc: u32,
    pub selected_vmd_mode: u32,
    pub selected_subcarriers: Vec<u32>,
    pub pca_iterations: u32,
    pub vmd_iterations: u32,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ProfileStage {
    ValidateCommitment,
    SelectSubcarriers,
    Bandpass,
    Pca,
    Vmd,
    Full,
}

impl ProfileStage {
    pub const ALL: [Self; 6] = [
        Self::ValidateCommitment,
        Self::SelectSubcarriers,
        Self::Bandpass,
        Self::Pca,
        Self::Vmd,
        Self::Full,
    ];

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ValidateCommitment => "validate_commitment",
            Self::SelectSubcarriers => "select_subcarriers",
            Self::Bandpass => "bandpass",
            Self::Pca => "pca",
            Self::Vmd => "vmd",
            Self::Full => "full",
        }
    }

    pub fn parse(value: &str) -> Result<Self, &'static str> {
        match value {
            "validate_commitment" => Ok(Self::ValidateCommitment),
            "select_subcarriers" => Ok(Self::SelectSubcarriers),
            "bandpass" => Ok(Self::Bandpass),
            "pca" => Ok(Self::Pca),
            "vmd" => Ok(Self::Vmd),
            "full" => Ok(Self::Full),
            _ => Err("unknown profile stage"),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub enum ProfileRequest {
    ValidateCommitment(PipelineInput),
    SelectSubcarriers(PipelineInput),
    Bandpass {
        input: PipelineInput,
        selected: Vec<usize>,
    },
    Pca {
        matrix: Vec<i64>,
        rows: usize,
        cols: usize,
    },
    Vmd {
        signal: Vec<i64>,
        sample_rate_hz: u32,
        min_bpm: u32,
        max_search_bpm: u32,
    },
    Full(PipelineInput),
}

impl ProfileRequest {
    pub const fn stage(&self) -> ProfileStage {
        match self {
            Self::ValidateCommitment(_) => ProfileStage::ValidateCommitment,
            Self::SelectSubcarriers(_) => ProfileStage::SelectSubcarriers,
            Self::Bandpass { .. } => ProfileStage::Bandpass,
            Self::Pca { .. } => ProfileStage::Pca,
            Self::Vmd { .. } => ProfileStage::Vmd,
            Self::Full(_) => ProfileStage::Full,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct StageCycleCount {
    pub stage: ProfileStage,
    pub cycles: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ProfileProcess {
    GuestInputDeserialize,
    ValidateFields,
    CommitmentHash,
    CommitmentCompare,
    SelectColumnExtraction,
    SelectCentering,
    SelectGoertzel,
    SelectTotalPower,
    SelectSortAndTruncate,
    BandpassColumnExtraction,
    BandpassLowMovingAverage,
    BandpassBaselineMovingAverage,
    BandpassCombine,
    PcaCentering,
    PcaCovariance,
    PcaPowerIteration,
    PcaProjection,
    VmdCentering,
    VmdGoertzelSpectrum,
    VmdClusteringIterations,
    VmdPeakModeSelection,
    OutputChecksum,
}

pub trait PipelineProfiler {
    fn enter(&mut self, process: ProfileProcess);
    fn exit(&mut self, process: ProfileProcess);
}

pub struct NoopProfiler;

impl PipelineProfiler for NoopProfiler {
    #[inline(always)]
    fn enter(&mut self, _process: ProfileProcess) {}

    #[inline(always)]
    fn exit(&mut self, _process: ProfileProcess) {}
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ProcessCycleCount {
    pub process: ProfileProcess,
    pub calls: u32,
    pub inclusive_cycles: u64,
    pub exclusive_cycles: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ProfileJournal {
    pub stage: ProfileStage,
    pub stage_cycles: Vec<StageCycleCount>,
    pub process_cycles: Vec<ProcessCycleCount>,
    pub output_len: usize,
    pub output_checksum: u64,
}

pub fn run_pipeline(input: &PipelineInput) -> Result<PipelineJournal, &'static str> {
    validate_and_check_commitment(input)?;

    let selected = select_subcarriers(input);
    let filtered = bandpass_selected(input, &selected);
    let respiration_pc = first_principal_component(&filtered, input.samples, selected.len());
    let (peak_bpm, mode_index) =
        vmd_spectral_decomposition(&respiration_pc, input.sample_rate_hz, input.bpm_min, 60);

    Ok(PipelineJournal {
        algorithm_version: ALGORITHM_VERSION.into(),
        input_commitment: input.input_commitment.clone(),
        breathing_rate_milli_bpm: peak_bpm.saturating_mul(1_000),
        peak_frequency_micro_hz: peak_bpm.saturating_mul(1_000_000) / 60,
        is_normal: peak_bpm >= input.bpm_min && peak_bpm <= input.bpm_max,
        selected_pc: 1,
        selected_vmd_mode: mode_index as u32,
        selected_subcarriers: selected.into_iter().map(|value| value as u32).collect(),
        pca_iterations: PCA_ITERATIONS as u32,
        vmd_iterations: VMD_ITERATIONS as u32,
    })
}

pub fn validate_input(input: &PipelineInput) -> Result<(), &'static str> {
    validate_input_profiled(input, &mut NoopProfiler)
}

pub fn validate_input_profiled<P: PipelineProfiler>(
    input: &PipelineInput,
    profiler: &mut P,
) -> Result<(), &'static str> {
    profiler.enter(ProfileProcess::ValidateFields);
    let result = (|| {
        if input.algorithm_version != ALGORITHM_VERSION {
            return Err("unsupported algorithm version");
        }
        if input.samples < 64 || input.subcarriers == 0 {
            return Err("CSI matrix is too small");
        }
        if input.amplitudes.len() != input.samples.saturating_mul(input.subcarriers) {
            return Err("CSI matrix shape mismatch");
        }
        if input.scale == 0 || input.sample_rate_hz == 0 || input.bpm_min > input.bpm_max {
            return Err("invalid pipeline parameters");
        }
        Ok(())
    })();
    profiler.exit(ProfileProcess::ValidateFields);
    result
}

pub fn validate_and_check_commitment(input: &PipelineInput) -> Result<(), &'static str> {
    validate_and_check_commitment_profiled(input, &mut NoopProfiler)
}

pub fn validate_and_check_commitment_profiled<P: PipelineProfiler>(
    input: &PipelineInput,
    profiler: &mut P,
) -> Result<(), &'static str> {
    validate_input_profiled(input, profiler)?;
    let calculated = commitment_profiled(input, profiler);
    profiler.enter(ProfileProcess::CommitmentCompare);
    let matches = calculated == input.input_commitment;
    profiler.exit(ProfileProcess::CommitmentCompare);
    if !matches {
        return Err("input commitment mismatch");
    }
    Ok(())
}

pub fn commitment(input: &PipelineInput) -> String {
    commitment_profiled(input, &mut NoopProfiler)
}

pub fn commitment_profiled<P: PipelineProfiler>(input: &PipelineInput, profiler: &mut P) -> String {
    profiler.enter(ProfileProcess::CommitmentHash);
    let mut digest = Sha256::new();
    digest.update((input.samples as u32).to_le_bytes());
    digest.update((input.subcarriers as u32).to_le_bytes());
    digest.update(input.scale.to_le_bytes());
    for value in &input.amplitudes {
        digest.update(value.to_le_bytes());
    }
    let output = hex_lower(&digest.finalize());
    profiler.exit(ProfileProcess::CommitmentHash);
    output
}

fn hex_lower(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output
}

pub fn select_subcarriers(input: &PipelineInput) -> Vec<usize> {
    select_subcarriers_profiled(input, &mut NoopProfiler)
}

pub fn select_subcarriers_profiled<P: PipelineProfiler>(
    input: &PipelineInput,
    profiler: &mut P,
) -> Vec<usize> {
    let mut scored = Vec::with_capacity(input.subcarriers);
    for carrier in 0..input.subcarriers {
        profiler.enter(ProfileProcess::SelectColumnExtraction);
        let signal = column(input, carrier);
        profiler.exit(ProfileProcess::SelectColumnExtraction);
        profiler.enter(ProfileProcess::SelectCentering);
        let centered = center(&signal);
        profiler.exit(ProfileProcess::SelectCentering);
        profiler.enter(ProfileProcess::SelectGoertzel);
        let mut breath_power = 0.0_f64;
        for bpm in (6..=60).step_by(3) {
            breath_power += goertzel_power(&centered, input.sample_rate_hz, bpm);
        }
        profiler.exit(ProfileProcess::SelectGoertzel);
        profiler.enter(ProfileProcess::SelectTotalPower);
        let total_power = centered
            .iter()
            .map(|value| (*value as f64) * (*value as f64))
            .sum::<f64>();
        let score = breath_power / (total_power + 1.0);
        profiler.exit(ProfileProcess::SelectTotalPower);
        scored.push((carrier, score));
    }
    profiler.enter(ProfileProcess::SelectSortAndTruncate);
    scored.sort_by(|left, right| {
        right
            .1
            .partial_cmp(&left.1)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.0.cmp(&right.0))
    });
    scored.truncate(core::cmp::min(MAX_SELECTED_SUBCARRIERS, input.subcarriers));
    let mut selected: Vec<usize> = scored.into_iter().map(|item| item.0).collect();
    selected.sort_unstable();
    profiler.exit(ProfileProcess::SelectSortAndTruncate);
    selected
}

fn column(input: &PipelineInput, carrier: usize) -> Vec<i64> {
    (0..input.samples)
        .map(|sample| input.amplitudes[sample * input.subcarriers + carrier] as i64)
        .collect()
}

fn center(signal: &[i64]) -> Vec<i64> {
    let mean = signal.iter().map(|value| *value as i128).sum::<i128>() / signal.len() as i128;
    signal.iter().map(|value| *value - mean as i64).collect()
}

pub fn bandpass_selected(input: &PipelineInput, selected: &[usize]) -> Vec<i64> {
    bandpass_selected_profiled(input, selected, &mut NoopProfiler)
}

pub fn bandpass_selected_profiled<P: PipelineProfiler>(
    input: &PipelineInput,
    selected: &[usize],
    profiler: &mut P,
) -> Vec<i64> {
    let mut output = vec![0_i64; input.samples * selected.len()];
    let low_window = core::cmp::max(3, input.sample_rate_hz as usize / 2); // about 2 Hz low-pass
    let high_window = core::cmp::max(low_window + 1, input.sample_rate_hz as usize * 5); // 0.2 Hz high-pass
    for (target_col, source_col) in selected.iter().enumerate() {
        profiler.enter(ProfileProcess::BandpassColumnExtraction);
        let signal = column(input, *source_col);
        profiler.exit(ProfileProcess::BandpassColumnExtraction);
        profiler.enter(ProfileProcess::BandpassLowMovingAverage);
        let low = moving_average(&signal, low_window);
        profiler.exit(ProfileProcess::BandpassLowMovingAverage);
        profiler.enter(ProfileProcess::BandpassBaselineMovingAverage);
        let baseline = moving_average(&low, high_window);
        profiler.exit(ProfileProcess::BandpassBaselineMovingAverage);
        profiler.enter(ProfileProcess::BandpassCombine);
        for sample in 0..input.samples {
            output[sample * selected.len() + target_col] = low[sample] - baseline[sample];
        }
        profiler.exit(ProfileProcess::BandpassCombine);
    }
    output
}

fn moving_average(signal: &[i64], window: usize) -> Vec<i64> {
    let mut result = vec![0_i64; signal.len()];
    let mut sum = 0_i128;
    for index in 0..signal.len() {
        sum += signal[index] as i128;
        if index >= window {
            sum -= signal[index - window] as i128;
        }
        let count = core::cmp::min(index + 1, window);
        result[index] = (sum / count as i128) as i64;
    }
    result
}

pub fn first_principal_component(matrix: &[i64], rows: usize, cols: usize) -> Vec<i64> {
    first_principal_component_profiled(matrix, rows, cols, &mut NoopProfiler)
}

pub fn first_principal_component_profiled<P: PipelineProfiler>(
    matrix: &[i64],
    rows: usize,
    cols: usize,
    profiler: &mut P,
) -> Vec<i64> {
    profiler.enter(ProfileProcess::PcaCentering);
    let mut centered = matrix.to_vec();
    for col in 0..cols {
        let mean = (0..rows)
            .map(|row| matrix[row * cols + col] as i128)
            .sum::<i128>()
            / rows as i128;
        for row in 0..rows {
            centered[row * cols + col] -= mean as i64;
        }
    }
    profiler.exit(ProfileProcess::PcaCentering);

    profiler.enter(ProfileProcess::PcaCovariance);
    let mut covariance = vec![0_i128; cols * cols];
    for left in 0..cols {
        for right in left..cols {
            let value = (0..rows)
                .map(|row| {
                    centered[row * cols + left] as i128 * centered[row * cols + right] as i128
                })
                .sum::<i128>();
            covariance[left * cols + right] = value;
            covariance[right * cols + left] = value;
        }
    }
    profiler.exit(ProfileProcess::PcaCovariance);

    profiler.enter(ProfileProcess::PcaPowerIteration);
    let mut vector = vec![1_000_000_i128; cols];
    for _ in 0..PCA_ITERATIONS {
        let next: Vec<i128> = (0..cols)
            .map(|row| {
                (0..cols)
                    .map(|col| covariance[row * cols + col] * vector[col] / 1_000_000)
                    .sum()
            })
            .collect();
        let max_abs = next
            .iter()
            .map(|value| value.abs())
            .max()
            .unwrap_or(1)
            .max(1);
        vector = next
            .into_iter()
            .map(|value| value * 1_000_000 / max_abs)
            .collect();
    }
    profiler.exit(ProfileProcess::PcaPowerIteration);

    profiler.enter(ProfileProcess::PcaProjection);
    let output = (0..rows)
        .map(|row| {
            let projected = (0..cols)
                .map(|col| centered[row * cols + col] as i128 * vector[col])
                .sum::<i128>()
                / 1_000_000;
            projected.clamp(i64::MIN as i128, i64::MAX as i128) as i64
        })
        .collect();
    profiler.exit(ProfileProcess::PcaProjection);
    output
}

pub fn vmd_spectral_decomposition(
    signal: &[i64],
    sample_rate_hz: u32,
    min_bpm: u32,
    max_search_bpm: u32,
) -> (u32, usize) {
    vmd_spectral_decomposition_profiled(
        signal,
        sample_rate_hz,
        min_bpm,
        max_search_bpm,
        &mut NoopProfiler,
    )
}

pub fn vmd_spectral_decomposition_profiled<P: PipelineProfiler>(
    signal: &[i64],
    sample_rate_hz: u32,
    min_bpm: u32,
    max_search_bpm: u32,
    profiler: &mut P,
) -> (u32, usize) {
    profiler.enter(ProfileProcess::VmdCentering);
    let centered = center(signal);
    profiler.exit(ProfileProcess::VmdCentering);
    profiler.enter(ProfileProcess::VmdGoertzelSpectrum);
    let frequencies: Vec<u32> = (min_bpm..=max_search_bpm).collect();
    let powers: Vec<f64> = frequencies
        .iter()
        .map(|bpm| goertzel_power(&centered, sample_rate_hz, *bpm))
        .collect();
    profiler.exit(ProfileProcess::VmdGoertzelSpectrum);
    profiler.enter(ProfileProcess::VmdClusteringIterations);
    let span = max_search_bpm.saturating_sub(min_bpm).max(1);
    let mut centers: Vec<f64> = (0..VMD_MODES)
        .map(|mode| min_bpm as f64 + span as f64 * mode as f64 / (VMD_MODES - 1) as f64)
        .collect();

    for _ in 0..VMD_ITERATIONS {
        let mut weighted = vec![0.0_f64; VMD_MODES];
        let mut totals = vec![0.0_f64; VMD_MODES];
        for (index, bpm) in frequencies.iter().enumerate() {
            let mode = centers
                .iter()
                .enumerate()
                .min_by(|left, right| {
                    let left_distance = (left.1 - *bpm as f64).abs();
                    let right_distance = (right.1 - *bpm as f64).abs();
                    left_distance
                        .partial_cmp(&right_distance)
                        .unwrap_or(Ordering::Equal)
                })
                .map(|item| item.0)
                .unwrap_or(0);
            weighted[mode] += powers[index] * *bpm as f64;
            totals[mode] += powers[index];
        }
        for mode in 0..VMD_MODES {
            if totals[mode] > 0.0 {
                centers[mode] = weighted[mode] / totals[mode];
            }
        }
    }
    profiler.exit(ProfileProcess::VmdClusteringIterations);

    profiler.enter(ProfileProcess::VmdPeakModeSelection);
    let (peak_index, _) = powers
        .iter()
        .enumerate()
        .max_by(|left, right| left.1.partial_cmp(right.1).unwrap_or(Ordering::Equal))
        .unwrap_or((0, &0.0));
    let peak_bpm = frequencies[peak_index];
    let mode_index = centers
        .iter()
        .enumerate()
        .min_by(|left, right| {
            (left.1 - peak_bpm as f64)
                .abs()
                .partial_cmp(&(right.1 - peak_bpm as f64).abs())
                .unwrap_or(Ordering::Equal)
        })
        .map(|item| item.0)
        .unwrap_or(0);
    profiler.exit(ProfileProcess::VmdPeakModeSelection);
    (peak_bpm, mode_index)
}

fn goertzel_power(signal: &[i64], sample_rate_hz: u32, bpm: u32) -> f64 {
    let omega = 2.0 * core::f64::consts::PI * bpm as f64 / 60.0 / sample_rate_hz as f64;
    let coefficient = 2.0 * libm::cos(omega);
    let mut previous = 0.0_f64;
    let mut previous2 = 0.0_f64;
    for value in signal {
        let current = *value as f64 + coefficient * previous - previous2;
        previous2 = previous;
        previous = current;
    }
    previous2 * previous2 + previous * previous - coefficient * previous * previous2
}

#[cfg(test)]
mod tests {
    use super::*;

    fn synthetic_input(breathing_bpm: u32) -> PipelineInput {
        let samples = 1_200;
        let subcarriers = 4;
        let mut amplitudes = Vec::with_capacity(samples * subcarriers);
        for sample in 0..samples {
            let time = sample as f64 / 100.0;
            for carrier in 0..subcarriers {
                let breathing =
                    libm::sin(2.0 * core::f64::consts::PI * breathing_bpm as f64 / 60.0 * time);
                let noise = libm::sin(2.0 * core::f64::consts::PI * (3.0 + carrier as f64) * time);
                amplitudes.push(
                    (5_000.0 + breathing * (900.0 - carrier as f64 * 80.0) + noise * 40.0) as i32,
                );
            }
        }
        let mut input = PipelineInput {
            samples,
            subcarriers,
            amplitudes,
            scale: 10_000,
            sample_rate_hz: 100,
            bpm_min: 6,
            bpm_max: 22,
            input_commitment: String::new(),
            algorithm_version: ALGORITHM_VERSION.into(),
        };
        input.input_commitment = commitment(&input);
        input
    }

    #[test]
    fn detects_normal_breathing_signal() {
        let result = run_pipeline(&synthetic_input(15)).expect("pipeline should run");
        assert!((14_000..=16_000).contains(&result.breathing_rate_milli_bpm));
        assert!(result.is_normal);
    }

    #[test]
    fn rejects_tampered_commitment() {
        let mut input = synthetic_input(15);
        input.amplitudes[0] += 1;
        assert_eq!(run_pipeline(&input), Err("input commitment mismatch"));
    }

    #[test]
    fn split_stages_match_end_to_end_pipeline() {
        let input = synthetic_input(15);
        validate_and_check_commitment(&input).expect("input should validate");
        let selected = select_subcarriers(&input);
        let filtered = bandpass_selected(&input, &selected);
        let principal_component =
            first_principal_component(&filtered, input.samples, selected.len());
        let (peak_bpm, mode_index) = vmd_spectral_decomposition(
            &principal_component,
            input.sample_rate_hz,
            input.bpm_min,
            60,
        );
        let result = run_pipeline(&input).expect("pipeline should run");

        assert_eq!(
            result.selected_subcarriers,
            selected
                .iter()
                .map(|value| *value as u32)
                .collect::<Vec<_>>()
        );
        assert_eq!(result.breathing_rate_milli_bpm, peak_bpm * 1_000);
        assert_eq!(result.selected_vmd_mode, mode_index as u32);
    }

    #[test]
    fn profile_stage_names_round_trip() {
        for stage in ProfileStage::ALL {
            assert_eq!(ProfileStage::parse(stage.as_str()), Ok(stage));
        }
    }
}
