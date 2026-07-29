extern crate alloc;

use alloc::vec::Vec;
use csi_zkvm_core::{
    PipelineInput, PipelineProfiler, ProcessCycleCount, ProfileJournal, ProfileProcess,
    ProfileRequest, ProfileStage, StageCycleCount, bandpass_selected_profiled,
    first_principal_component_profiled, select_subcarriers_profiled,
    validate_and_check_commitment_profiled, vmd_spectral_decomposition_profiled,
};
use risc0_zkvm::guest::env;

struct ActiveSpan {
    process: ProfileProcess,
    start: u64,
    child_cycles: u64,
}

#[derive(Default)]
struct CycleProfiler {
    active: Vec<ActiveSpan>,
    records: Vec<ProcessCycleCount>,
}

impl CycleProfiler {
    fn record(&mut self, process: ProfileProcess, inclusive_cycles: u64, exclusive_cycles: u64) {
        if let Some(record) = self
            .records
            .iter_mut()
            .find(|record| record.process == process)
        {
            record.calls = record.calls.saturating_add(1);
            record.inclusive_cycles = record.inclusive_cycles.saturating_add(inclusive_cycles);
            record.exclusive_cycles = record.exclusive_cycles.saturating_add(exclusive_cycles);
        } else {
            self.records.push(ProcessCycleCount {
                process,
                calls: 1,
                inclusive_cycles,
                exclusive_cycles,
            });
        }
    }

    fn record_external(&mut self, process: ProfileProcess, cycles: u64) {
        self.record(process, cycles, cycles);
    }

    fn into_records(self) -> Vec<ProcessCycleCount> {
        assert!(self.active.is_empty(), "unclosed profiling span");
        self.records
    }
}

impl PipelineProfiler for CycleProfiler {
    fn enter(&mut self, process: ProfileProcess) {
        self.active.push(ActiveSpan {
            process,
            start: env::cycle_count(),
            child_cycles: 0,
        });
    }

    fn exit(&mut self, process: ProfileProcess) {
        let end = env::cycle_count();
        let span = self.active.pop().expect("profiling stack underflow");
        assert_eq!(span.process, process, "profiling stack mismatch");
        let inclusive = end.saturating_sub(span.start);
        let exclusive = inclusive.saturating_sub(span.child_cycles);
        if let Some(parent) = self.active.last_mut() {
            parent.child_cycles = parent.child_cycles.saturating_add(inclusive);
        }
        self.record(process, inclusive, exclusive);
    }
}

fn elapsed(start: u64) -> u64 {
    env::cycle_count().saturating_sub(start)
}

fn checksum_i64(values: &[i64]) -> u64 {
    values.iter().fold(0xcbf29ce484222325_u64, |hash, value| {
        (hash ^ *value as u64).wrapping_mul(0x100000001b3)
    })
}

fn checksum_usize(values: &[usize]) -> u64 {
    values.iter().fold(0xcbf29ce484222325_u64, |hash, value| {
        (hash ^ *value as u64).wrapping_mul(0x100000001b3)
    })
}

fn read_request() -> (ProfileRequest, CycleProfiler) {
    let deserialize_start = env::cycle_count();
    let request: ProfileRequest = env::read();
    let deserialize_cycles = elapsed(deserialize_start);
    let mut profiler = CycleProfiler::default();
    profiler.record_external(ProfileProcess::GuestInputDeserialize, deserialize_cycles);
    (request, profiler)
}

fn commit_result(
    stage: ProfileStage,
    function_cycles: u64,
    output_len: usize,
    output_checksum: u64,
    profiler: CycleProfiler,
) {
    let journal = ProfileJournal {
        stage,
        stage_cycles: alloc::vec![StageCycleCount {
            stage,
            cycles: function_cycles,
        }],
        process_cycles: profiler.into_records(),
        output_len,
        output_checksum,
    };
    env::commit(&journal);
}

pub fn run_validate_commitment() {
    let (request, mut profiler) = read_request();
    let ProfileRequest::ValidateCommitment(input) = request else {
        panic!("validate guest received the wrong request type");
    };
    let start = env::cycle_count();
    validate_and_check_commitment_profiled(&input, &mut profiler)
        .expect("profile input validation failed");
    let function_cycles = elapsed(start);
    profiler.enter(ProfileProcess::OutputChecksum);
    let checksum = input.input_commitment.len() as u64;
    profiler.exit(ProfileProcess::OutputChecksum);
    commit_result(
        ProfileStage::ValidateCommitment,
        function_cycles,
        input.amplitudes.len(),
        checksum,
        profiler,
    );
}

pub fn run_select_subcarriers() {
    let (request, mut profiler) = read_request();
    let ProfileRequest::SelectSubcarriers(input) = request else {
        panic!("subcarrier guest received the wrong request type");
    };
    let start = env::cycle_count();
    let selected = select_subcarriers_profiled(&input, &mut profiler);
    let function_cycles = elapsed(start);
    profiler.enter(ProfileProcess::OutputChecksum);
    let checksum = checksum_usize(&selected);
    profiler.exit(ProfileProcess::OutputChecksum);
    commit_result(
        ProfileStage::SelectSubcarriers,
        function_cycles,
        selected.len(),
        checksum,
        profiler,
    );
}

pub fn run_bandpass() {
    let (request, mut profiler) = read_request();
    let ProfileRequest::Bandpass { input, selected } = request else {
        panic!("bandpass guest received the wrong request type");
    };
    let start = env::cycle_count();
    let filtered = bandpass_selected_profiled(&input, &selected, &mut profiler);
    let function_cycles = elapsed(start);
    profiler.enter(ProfileProcess::OutputChecksum);
    let checksum = checksum_i64(&filtered);
    profiler.exit(ProfileProcess::OutputChecksum);
    commit_result(
        ProfileStage::Bandpass,
        function_cycles,
        filtered.len(),
        checksum,
        profiler,
    );
}

pub fn run_pca() {
    let (request, mut profiler) = read_request();
    let ProfileRequest::Pca { matrix, rows, cols } = request else {
        panic!("PCA guest received the wrong request type");
    };
    let start = env::cycle_count();
    let principal_component =
        first_principal_component_profiled(&matrix, rows, cols, &mut profiler);
    let function_cycles = elapsed(start);
    profiler.enter(ProfileProcess::OutputChecksum);
    let checksum = checksum_i64(&principal_component);
    profiler.exit(ProfileProcess::OutputChecksum);
    commit_result(
        ProfileStage::Pca,
        function_cycles,
        principal_component.len(),
        checksum,
        profiler,
    );
}

pub fn run_vmd() {
    let (request, mut profiler) = read_request();
    let ProfileRequest::Vmd {
        signal,
        sample_rate_hz,
        min_bpm,
        max_search_bpm,
    } = request
    else {
        panic!("VMD guest received the wrong request type");
    };
    let start = env::cycle_count();
    let (peak_bpm, mode_index) = vmd_spectral_decomposition_profiled(
        &signal,
        sample_rate_hz,
        min_bpm,
        max_search_bpm,
        &mut profiler,
    );
    let function_cycles = elapsed(start);
    profiler.enter(ProfileProcess::OutputChecksum);
    let checksum = ((peak_bpm as u64) << 32) | mode_index as u64;
    profiler.exit(ProfileProcess::OutputChecksum);
    commit_result(
        ProfileStage::Vmd,
        function_cycles,
        2,
        checksum,
        profiler,
    );
}

pub fn run_combined() {
    let (request, mut profiler) = read_request();
    let stage = request.stage();
    let (stage_cycles, output_len, output_checksum) = match request {
        ProfileRequest::ValidateCommitment(input) => {
            let start = env::cycle_count();
            validate_and_check_commitment_profiled(&input, &mut profiler)
                .expect("profile input validation failed");
            let function_cycles = elapsed(start);
            profiler.enter(ProfileProcess::OutputChecksum);
            let checksum = input.input_commitment.len() as u64;
            profiler.exit(ProfileProcess::OutputChecksum);
            (
                alloc::vec![StageCycleCount {
                    stage,
                    cycles: function_cycles,
                }],
                input.amplitudes.len(),
                checksum,
            )
        }
        ProfileRequest::SelectSubcarriers(input) => {
            let start = env::cycle_count();
            let selected = select_subcarriers_profiled(&input, &mut profiler);
            let function_cycles = elapsed(start);
            profiler.enter(ProfileProcess::OutputChecksum);
            let checksum = checksum_usize(&selected);
            profiler.exit(ProfileProcess::OutputChecksum);
            (
                alloc::vec![StageCycleCount {
                    stage,
                    cycles: function_cycles,
                }],
                selected.len(),
                checksum,
            )
        }
        ProfileRequest::Bandpass { input, selected } => {
            let start = env::cycle_count();
            let filtered = bandpass_selected_profiled(&input, &selected, &mut profiler);
            let function_cycles = elapsed(start);
            profiler.enter(ProfileProcess::OutputChecksum);
            let checksum = checksum_i64(&filtered);
            profiler.exit(ProfileProcess::OutputChecksum);
            (
                alloc::vec![StageCycleCount {
                    stage,
                    cycles: function_cycles,
                }],
                filtered.len(),
                checksum,
            )
        }
        ProfileRequest::Pca { matrix, rows, cols } => {
            let start = env::cycle_count();
            let principal_component =
                first_principal_component_profiled(&matrix, rows, cols, &mut profiler);
            let function_cycles = elapsed(start);
            profiler.enter(ProfileProcess::OutputChecksum);
            let checksum = checksum_i64(&principal_component);
            profiler.exit(ProfileProcess::OutputChecksum);
            (
                alloc::vec![StageCycleCount {
                    stage,
                    cycles: function_cycles,
                }],
                principal_component.len(),
                checksum,
            )
        }
        ProfileRequest::Vmd {
            signal,
            sample_rate_hz,
            min_bpm,
            max_search_bpm,
        } => {
            let start = env::cycle_count();
            let (peak_bpm, mode_index) = vmd_spectral_decomposition_profiled(
                &signal,
                sample_rate_hz,
                min_bpm,
                max_search_bpm,
                &mut profiler,
            );
            let function_cycles = elapsed(start);
            profiler.enter(ProfileProcess::OutputChecksum);
            let checksum = ((peak_bpm as u64) << 32) | mode_index as u64;
            profiler.exit(ProfileProcess::OutputChecksum);
            (
                alloc::vec![StageCycleCount {
                    stage,
                    cycles: function_cycles,
                }],
                2,
                checksum,
            )
        }
        ProfileRequest::Full(input) => run_full_profile(input, &mut profiler),
    };

    let journal = ProfileJournal {
        stage,
        stage_cycles,
        process_cycles: profiler.into_records(),
        output_len,
        output_checksum,
    };
    env::commit(&journal);
}

fn run_full_profile(
    input: PipelineInput,
    profiler: &mut CycleProfiler,
) -> (Vec<StageCycleCount>, usize, u64) {
    let mut stage_cycles = Vec::with_capacity(5);

    let start = env::cycle_count();
    validate_and_check_commitment_profiled(&input, profiler)
        .expect("profile input validation failed");
    stage_cycles.push(StageCycleCount {
        stage: ProfileStage::ValidateCommitment,
        cycles: elapsed(start),
    });

    let start = env::cycle_count();
    let selected = select_subcarriers_profiled(&input, profiler);
    stage_cycles.push(StageCycleCount {
        stage: ProfileStage::SelectSubcarriers,
        cycles: elapsed(start),
    });

    let start = env::cycle_count();
    let filtered = bandpass_selected_profiled(&input, &selected, profiler);
    stage_cycles.push(StageCycleCount {
        stage: ProfileStage::Bandpass,
        cycles: elapsed(start),
    });

    let start = env::cycle_count();
    let principal_component =
        first_principal_component_profiled(&filtered, input.samples, selected.len(), profiler);
    stage_cycles.push(StageCycleCount {
        stage: ProfileStage::Pca,
        cycles: elapsed(start),
    });

    let start = env::cycle_count();
    let (peak_bpm, mode_index) = vmd_spectral_decomposition_profiled(
        &principal_component,
        input.sample_rate_hz,
        input.bpm_min,
        60,
        profiler,
    );
    stage_cycles.push(StageCycleCount {
        stage: ProfileStage::Vmd,
        cycles: elapsed(start),
    });

    profiler.enter(ProfileProcess::OutputChecksum);
    let output_checksum =
        checksum_i64(&principal_component) ^ ((peak_bpm as u64) << 32) ^ mode_index as u64;
    profiler.exit(ProfileProcess::OutputChecksum);
    (stage_cycles, principal_component.len(), output_checksum)
}
