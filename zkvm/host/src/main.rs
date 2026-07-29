use std::{
    env, fs,
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU64, Ordering},
    },
    thread,
    time::{Duration, Instant},
};

use anyhow::{Context, Result, bail};
use base64::{Engine as _, engine::general_purpose::STANDARD};
use csi_zkvm_core::{
    PipelineInput, PipelineJournal, ProfileJournal, ProfileProcess, ProfileRequest, ProfileStage,
    bandpass_selected, first_principal_component, select_subcarriers,
    validate_and_check_commitment,
};
use csi_zkvm_methods::{
    CSI_BANDPASS_PROFILE_ELF, CSI_BANDPASS_PROFILE_ID, CSI_BREATHING_GUEST_ELF,
    CSI_BREATHING_GUEST_ID, CSI_BREATHING_PROFILE_ELF, CSI_BREATHING_PROFILE_ID,
    CSI_PCA_PROFILE_ELF, CSI_PCA_PROFILE_ID, CSI_SELECT_SUBCARRIERS_PROFILE_ELF,
    CSI_SELECT_SUBCARRIERS_PROFILE_ID, CSI_VALIDATE_COMMITMENT_PROFILE_ELF,
    CSI_VALIDATE_COMMITMENT_PROFILE_ID, CSI_VMD_PROFILE_ELF, CSI_VMD_PROFILE_ID,
};
use risc0_zkvm::{ExecutorEnv, default_executor, default_prover};
use serde::Serialize;

#[derive(Serialize)]
struct ProverOutput {
    receipt: String,
    journal: PipelineJournal,
    #[serde(rename = "isNormal")]
    is_normal: bool,
    #[serde(rename = "isValid")]
    is_valid: bool,
    method: &'static str,
    prove_seconds: f64,
    verify_seconds: f64,
    user_cycles: u64,
    total_cycles: u64,
    segments: usize,
    input_file_read_seconds: f64,
    input_json_decode_seconds: f64,
    executor_env_build_seconds: f64,
    journal_decode_seconds: f64,
    receipt_serialize_seconds: f64,
    output_json_serialize_seconds: f64,
    total_host_seconds: f64,
}

#[derive(Serialize)]
struct SegmentOutput {
    po2: u32,
    cycles: u32,
}

#[derive(Serialize)]
struct ProofStatsOutput {
    segments: usize,
    total_cycles: u64,
    user_cycles: u64,
    paging_cycles: u64,
    reserved_cycles: u64,
}

#[derive(Serialize)]
struct ProfileOutput {
    stage: ProfileStage,
    samples: usize,
    subcarriers: usize,
    input_elements: usize,
    input_file_read_seconds: f64,
    input_json_decode_seconds: f64,
    request_bytes: usize,
    request_serialize_seconds: f64,
    host_prepare_seconds: f64,
    execution_env_build_seconds: f64,
    execution_seconds: f64,
    execution_user_cycles: u64,
    execution_segments: Vec<SegmentOutput>,
    execution_journal_decode_seconds: f64,
    proving_env_build_seconds: f64,
    proving_seconds: f64,
    verification_seconds: f64,
    proof_journal_decode_seconds: f64,
    receipt_bytes: usize,
    receipt_serialize_seconds: f64,
    guest_profiled_cycles: u64,
    guest_unattributed_cycles: u64,
    proof_stats: ProofStatsOutput,
    journal: ProfileJournal,
    method: &'static str,
    output_json_serialize_seconds: f64,
    total_host_seconds: f64,
}

#[derive(Serialize)]
struct IsolatedProfileOutput {
    stage: ProfileStage,
    source_samples: usize,
    source_subcarriers: usize,
    source_input_elements: usize,
    request_input_elements: usize,
    input_file_read_seconds: f64,
    input_json_decode_seconds: f64,
    request_bytes: usize,
    request_serialize_seconds: f64,
    host_dependency_prepare_seconds: f64,
    proving_env_build_seconds: f64,
    proving_seconds: f64,
    proving_memory: PeakMemoryOutput,
    verification_seconds: f64,
    proof_journal_decode_seconds: f64,
    receipt_bytes: usize,
    receipt_serialize_seconds: f64,
    guest_profiled_cycles: u64,
    guest_unattributed_cycles: u64,
    proof_stats: ProofStatsOutput,
    journal: ProfileJournal,
    method: &'static str,
    dependency_policy: &'static str,
    output_json_serialize_seconds: f64,
    total_host_seconds: f64,
}

#[derive(Default, Serialize)]
struct PeakMemoryOutput {
    peak_rss_bytes: Option<u64>,
    peak_virtual_memory_bytes: Option<u64>,
    cgroup_memory_at_start_bytes: Option<u64>,
    cgroup_memory_peak_bytes: Option<u64>,
    cgroup_memory_delta_peak_bytes: Option<u64>,
    sample_interval_milliseconds: u64,
}

struct MemoryMonitor {
    stop: Arc<AtomicBool>,
    handle: thread::JoinHandle<PeakMemoryOutput>,
}

fn update_max(target: &AtomicU64, value: u64) {
    let mut current = target.load(Ordering::Relaxed);
    while value > current {
        match target.compare_exchange_weak(current, value, Ordering::Relaxed, Ordering::Relaxed) {
            Ok(_) => break,
            Err(observed) => current = observed,
        }
    }
}

fn read_process_memory() -> (Option<u64>, Option<u64>) {
    let Ok(status) = fs::read_to_string("/proc/self/status") else {
        return (None, None);
    };
    let mut rss = None;
    let mut virtual_memory = None;
    for line in status.lines() {
        let (name, raw) = match line.split_once(':') {
            Some(parts) => parts,
            None => continue,
        };
        let Some(value) = raw.split_whitespace().next() else {
            continue;
        };
        let Ok(kibibytes) = value.parse::<u64>() else {
            continue;
        };
        match name {
            "VmRSS" => rss = Some(kibibytes.saturating_mul(1024)),
            "VmSize" => virtual_memory = Some(kibibytes.saturating_mul(1024)),
            _ => {}
        }
    }
    (rss, virtual_memory)
}

fn read_cgroup_memory() -> Option<u64> {
    fs::read_to_string("/sys/fs/cgroup/memory.current")
        .ok()?
        .trim()
        .parse()
        .ok()
}

impl MemoryMonitor {
    fn start() -> Self {
        const SAMPLE_INTERVAL_MILLISECONDS: u64 = 50;
        let stop = Arc::new(AtomicBool::new(false));
        let thread_stop = Arc::clone(&stop);
        let cgroup_start = read_cgroup_memory();
        let handle = thread::spawn(move || {
            let peak_rss = AtomicU64::new(0);
            let peak_virtual = AtomicU64::new(0);
            let peak_cgroup = AtomicU64::new(cgroup_start.unwrap_or(0));
            loop {
                let (rss, virtual_memory) = read_process_memory();
                if let Some(value) = rss {
                    update_max(&peak_rss, value);
                }
                if let Some(value) = virtual_memory {
                    update_max(&peak_virtual, value);
                }
                if let Some(value) = read_cgroup_memory() {
                    update_max(&peak_cgroup, value);
                }
                if thread_stop.load(Ordering::Relaxed) {
                    break;
                }
                thread::sleep(Duration::from_millis(SAMPLE_INTERVAL_MILLISECONDS));
            }
            let peak_rss = peak_rss.load(Ordering::Relaxed);
            let peak_virtual = peak_virtual.load(Ordering::Relaxed);
            let peak_cgroup = peak_cgroup.load(Ordering::Relaxed);
            PeakMemoryOutput {
                peak_rss_bytes: (peak_rss > 0).then_some(peak_rss),
                peak_virtual_memory_bytes: (peak_virtual > 0).then_some(peak_virtual),
                cgroup_memory_at_start_bytes: cgroup_start,
                cgroup_memory_peak_bytes: (peak_cgroup > 0).then_some(peak_cgroup),
                cgroup_memory_delta_peak_bytes: cgroup_start
                    .map(|start| peak_cgroup.saturating_sub(start)),
                sample_interval_milliseconds: SAMPLE_INTERVAL_MILLISECONDS,
            }
        });
        Self { stop, handle }
    }

    fn stop(self) -> PeakMemoryOutput {
        self.stop.store(true, Ordering::Relaxed);
        self.handle.join().unwrap_or_default()
    }
}

struct LoadedInput {
    input: PipelineInput,
    file_read_seconds: f64,
    json_decode_seconds: f64,
}

fn main() -> Result<()> {
    let args: Vec<String> = env::args().skip(1).collect();
    match args.as_slice() {
        [command, input_path] if command == "prove" => prove(PathBuf::from(input_path)),
        [command, stage, input_path] if command == "profile-stage" => {
            profile_stage(stage, PathBuf::from(input_path))
        }
        [command, stage, input_path] if command == "profile-isolated" => {
            profile_isolated(stage, PathBuf::from(input_path))
        }
        _ => bail!(
            "usage:\n  csi-zkvm-host prove <pipeline-input.json>\n  \
             csi-zkvm-host profile-stage \
             <validate_commitment|select_subcarriers|bandpass|pca|vmd|full> \
             <pipeline-input.json>\n  \
             csi-zkvm-host profile-isolated \
             <validate_commitment|select_subcarriers|bandpass|pca|vmd> \
             <pipeline-input.json>"
        ),
    }
}

fn read_input(input_path: PathBuf) -> Result<LoadedInput> {
    let read_start = Instant::now();
    let input_bytes = fs::read(input_path).context("failed to read input")?;
    let file_read_seconds = read_start.elapsed().as_secs_f64();
    let decode_start = Instant::now();
    let input: PipelineInput =
        serde_json::from_slice(&input_bytes).context("invalid pipeline input")?;
    let json_decode_seconds = decode_start.elapsed().as_secs_f64();
    Ok(LoadedInput {
        input,
        file_read_seconds,
        json_decode_seconds,
    })
}

fn prove(input_path: PathBuf) -> Result<()> {
    let total_start = Instant::now();
    let loaded = read_input(input_path)?;
    let input = loaded.input;
    let env_start = Instant::now();
    let executor_env = ExecutorEnv::builder().write(&input)?.build()?;
    let executor_env_build_seconds = env_start.elapsed().as_secs_f64();
    let prove_start = Instant::now();
    let prove_info = default_prover()
        .prove(executor_env, CSI_BREATHING_GUEST_ELF)
        .context("RISC Zero proof generation failed")?;
    let prove_seconds = prove_start.elapsed().as_secs_f64();
    let receipt = prove_info.receipt;
    let verify_start = Instant::now();
    receipt
        .verify(CSI_BREATHING_GUEST_ID)
        .context("locally generated receipt did not verify")?;
    let verify_seconds = verify_start.elapsed().as_secs_f64();
    let journal_start = Instant::now();
    let journal: PipelineJournal = receipt.journal.decode().context("invalid guest journal")?;
    let journal_decode_seconds = journal_start.elapsed().as_secs_f64();
    let receipt_serialize_start = Instant::now();
    let encoded_receipt = STANDARD.encode(bincode::serialize(&receipt)?);
    let receipt_serialize_seconds = receipt_serialize_start.elapsed().as_secs_f64();
    let mut output = ProverOutput {
        is_normal: journal.is_normal,
        is_valid: true,
        receipt: encoded_receipt,
        journal,
        method: "risc0_5_1_fixed_v1",
        prove_seconds,
        verify_seconds,
        user_cycles: prove_info.stats.user_cycles,
        total_cycles: prove_info.stats.total_cycles,
        segments: prove_info.stats.segments,
        input_file_read_seconds: loaded.file_read_seconds,
        input_json_decode_seconds: loaded.json_decode_seconds,
        executor_env_build_seconds,
        journal_decode_seconds,
        receipt_serialize_seconds,
        output_json_serialize_seconds: 0.0,
        total_host_seconds: total_start.elapsed().as_secs_f64(),
    };
    let output_serialize_start = Instant::now();
    let _ = serde_json::to_string(&output)?;
    output.output_json_serialize_seconds = output_serialize_start.elapsed().as_secs_f64();
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

fn prepare_profile_request(stage: ProfileStage, input: PipelineInput) -> Result<ProfileRequest> {
    validate_and_check_commitment(&input).map_err(anyhow::Error::msg)?;
    Ok(match stage {
        ProfileStage::ValidateCommitment => ProfileRequest::ValidateCommitment(input),
        ProfileStage::SelectSubcarriers => ProfileRequest::SelectSubcarriers(input),
        ProfileStage::Bandpass => {
            let selected = select_subcarriers(&input);
            ProfileRequest::Bandpass { input, selected }
        }
        ProfileStage::Pca => {
            let selected = select_subcarriers(&input);
            let rows = input.samples;
            let cols = selected.len();
            let matrix = bandpass_selected(&input, &selected);
            ProfileRequest::Pca { matrix, rows, cols }
        }
        ProfileStage::Vmd => {
            let selected = select_subcarriers(&input);
            let filtered = bandpass_selected(&input, &selected);
            let signal = first_principal_component(&filtered, input.samples, selected.len());
            ProfileRequest::Vmd {
                signal,
                sample_rate_hz: input.sample_rate_hz,
                min_bpm: input.bpm_min,
                max_search_bpm: 60,
            }
        }
        ProfileStage::Full => ProfileRequest::Full(input),
    })
}

fn compact_selected_input(input: &PipelineInput, selected: &[usize]) -> PipelineInput {
    let mut amplitudes = Vec::with_capacity(input.samples.saturating_mul(selected.len()));
    for row in 0..input.samples {
        let offset = row * input.subcarriers;
        for &column in selected {
            amplitudes.push(input.amplitudes[offset + column]);
        }
    }
    PipelineInput {
        samples: input.samples,
        subcarriers: selected.len(),
        amplitudes,
        scale: input.scale,
        sample_rate_hz: input.sample_rate_hz,
        bpm_min: input.bpm_min,
        bpm_max: input.bpm_max,
        input_commitment: input.input_commitment.clone(),
        algorithm_version: input.algorithm_version.clone(),
    }
}

fn prepare_isolated_profile_request(
    stage: ProfileStage,
    input: PipelineInput,
) -> Result<ProfileRequest> {
    validate_and_check_commitment(&input).map_err(anyhow::Error::msg)?;
    Ok(match stage {
        ProfileStage::ValidateCommitment => ProfileRequest::ValidateCommitment(input),
        ProfileStage::SelectSubcarriers => ProfileRequest::SelectSubcarriers(input),
        ProfileStage::Bandpass => {
            let selected = select_subcarriers(&input);
            let compact = compact_selected_input(&input, &selected);
            let compact_columns = (0..selected.len()).collect();
            ProfileRequest::Bandpass {
                input: compact,
                selected: compact_columns,
            }
        }
        ProfileStage::Pca => {
            let selected = select_subcarriers(&input);
            let rows = input.samples;
            let cols = selected.len();
            let matrix = bandpass_selected(&input, &selected);
            ProfileRequest::Pca { matrix, rows, cols }
        }
        ProfileStage::Vmd => {
            let selected = select_subcarriers(&input);
            let filtered = bandpass_selected(&input, &selected);
            let signal = first_principal_component(&filtered, input.samples, selected.len());
            ProfileRequest::Vmd {
                signal,
                sample_rate_hz: input.sample_rate_hz,
                min_bpm: input.bpm_min,
                max_search_bpm: 60,
            }
        }
        ProfileStage::Full => bail!("full is not an isolated guest stage"),
    })
}

fn request_input_elements(request: &ProfileRequest) -> usize {
    match request {
        ProfileRequest::ValidateCommitment(input)
        | ProfileRequest::SelectSubcarriers(input)
        | ProfileRequest::Full(input) => input.amplitudes.len(),
        ProfileRequest::Bandpass { input, .. } => input.amplitudes.len(),
        ProfileRequest::Pca { matrix, .. } => matrix.len(),
        ProfileRequest::Vmd { signal, .. } => signal.len(),
    }
}

fn isolated_elf(stage: ProfileStage) -> Result<&'static [u8]> {
    Ok(match stage {
        ProfileStage::ValidateCommitment => CSI_VALIDATE_COMMITMENT_PROFILE_ELF,
        ProfileStage::SelectSubcarriers => CSI_SELECT_SUBCARRIERS_PROFILE_ELF,
        ProfileStage::Bandpass => CSI_BANDPASS_PROFILE_ELF,
        ProfileStage::Pca => CSI_PCA_PROFILE_ELF,
        ProfileStage::Vmd => CSI_VMD_PROFILE_ELF,
        ProfileStage::Full => bail!("full has no isolated guest"),
    })
}

fn verify_isolated_receipt(stage: ProfileStage, receipt: &risc0_zkvm::Receipt) -> Result<()> {
    match stage {
        ProfileStage::ValidateCommitment => receipt.verify(CSI_VALIDATE_COMMITMENT_PROFILE_ID),
        ProfileStage::SelectSubcarriers => receipt.verify(CSI_SELECT_SUBCARRIERS_PROFILE_ID),
        ProfileStage::Bandpass => receipt.verify(CSI_BANDPASS_PROFILE_ID),
        ProfileStage::Pca => receipt.verify(CSI_PCA_PROFILE_ID),
        ProfileStage::Vmd => receipt.verify(CSI_VMD_PROFILE_ID),
        ProfileStage::Full => bail!("full has no isolated guest"),
    }
    .context("isolated profiling receipt did not verify")
}

fn profile_isolated(stage_name: &str, input_path: PathBuf) -> Result<()> {
    let total_start = Instant::now();
    let stage = ProfileStage::parse(stage_name).map_err(anyhow::Error::msg)?;
    if stage == ProfileStage::Full {
        bail!("full is not supported by profile-isolated");
    }
    let elf = isolated_elf(stage)?;
    let loaded = read_input(input_path)?;
    let source_samples = loaded.input.samples;
    let source_subcarriers = loaded.input.subcarriers;
    let source_input_elements = loaded.input.amplitudes.len();

    let prepare_start = Instant::now();
    let request = prepare_isolated_profile_request(stage, loaded.input)?;
    let host_dependency_prepare_seconds = prepare_start.elapsed().as_secs_f64();
    let request_input_elements = request_input_elements(&request);
    let request_serialize_start = Instant::now();
    let request_bytes = bincode::serialize(&request)?.len();
    let request_serialize_seconds = request_serialize_start.elapsed().as_secs_f64();

    let proving_env_start = Instant::now();
    let proving_env = ExecutorEnv::builder().write(&request)?.build()?;
    let proving_env_build_seconds = proving_env_start.elapsed().as_secs_f64();
    let proving_start = Instant::now();
    let memory_monitor = MemoryMonitor::start();
    let proof_result = default_prover()
        .prove(proving_env, elf)
        .context("isolated profiling proof failed");
    let proving_seconds = proving_start.elapsed().as_secs_f64();
    let proving_memory = memory_monitor.stop();
    let prove_info = proof_result?;

    let verification_start = Instant::now();
    verify_isolated_receipt(stage, &prove_info.receipt)?;
    let verification_seconds = verification_start.elapsed().as_secs_f64();
    let proof_journal_decode_start = Instant::now();
    let journal: ProfileJournal = prove_info
        .receipt
        .journal
        .decode()
        .context("invalid isolated profiling journal")?;
    let proof_journal_decode_seconds = proof_journal_decode_start.elapsed().as_secs_f64();
    if journal.stage != stage {
        bail!("isolated profiling journal returned a different stage");
    }

    let receipt_serialize_start = Instant::now();
    let receipt_bytes = bincode::serialize(&prove_info.receipt)?.len();
    let receipt_serialize_seconds = receipt_serialize_start.elapsed().as_secs_f64();
    let stage_function_cycles = journal
        .stage_cycles
        .iter()
        .map(|entry| entry.cycles)
        .sum::<u64>();
    let non_stage_profile_cycles = journal
        .process_cycles
        .iter()
        .filter(|entry| {
            matches!(
                entry.process,
                ProfileProcess::GuestInputDeserialize | ProfileProcess::OutputChecksum
            )
        })
        .map(|entry| entry.inclusive_cycles)
        .sum::<u64>();
    let guest_profiled_cycles = stage_function_cycles.saturating_add(non_stage_profile_cycles);
    let guest_unattributed_cycles = prove_info
        .stats
        .user_cycles
        .saturating_sub(guest_profiled_cycles);

    let mut output = IsolatedProfileOutput {
        stage,
        source_samples,
        source_subcarriers,
        source_input_elements,
        request_input_elements,
        input_file_read_seconds: loaded.file_read_seconds,
        input_json_decode_seconds: loaded.json_decode_seconds,
        request_bytes,
        request_serialize_seconds,
        host_dependency_prepare_seconds,
        proving_env_build_seconds,
        proving_seconds,
        proving_memory,
        verification_seconds,
        proof_journal_decode_seconds,
        receipt_bytes,
        receipt_serialize_seconds,
        guest_profiled_cycles,
        guest_unattributed_cycles,
        proof_stats: ProofStatsOutput {
            segments: prove_info.stats.segments,
            total_cycles: prove_info.stats.total_cycles,
            user_cycles: prove_info.stats.user_cycles,
            paging_cycles: prove_info.stats.paging_cycles,
            reserved_cycles: prove_info.stats.reserved_cycles,
        },
        journal,
        method: "risc0_isolated_stage_profile_v1",
        dependency_policy: ("前段のproof結果には依存せず、同じcore関数をhostで実行して当該guestの直接入力を作る。"),
        output_json_serialize_seconds: 0.0,
        total_host_seconds: total_start.elapsed().as_secs_f64(),
    };
    let output_serialize_start = Instant::now();
    let _ = serde_json::to_string(&output)?;
    output.output_json_serialize_seconds = output_serialize_start.elapsed().as_secs_f64();
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

fn profile_stage(stage_name: &str, input_path: PathBuf) -> Result<()> {
    let total_start = Instant::now();
    let stage = ProfileStage::parse(stage_name).map_err(anyhow::Error::msg)?;
    let loaded = read_input(input_path)?;
    let input = loaded.input;
    let samples = input.samples;
    let subcarriers = input.subcarriers;
    let input_elements = input.amplitudes.len();

    let prepare_start = Instant::now();
    let request = prepare_profile_request(stage, input)?;
    let host_prepare_seconds = prepare_start.elapsed().as_secs_f64();
    let request_serialize_start = Instant::now();
    let request_bytes = bincode::serialize(&request)?.len();
    let request_serialize_seconds = request_serialize_start.elapsed().as_secs_f64();

    let execution_env_start = Instant::now();
    let execution_env = ExecutorEnv::builder().write(&request)?.build()?;
    let execution_env_build_seconds = execution_env_start.elapsed().as_secs_f64();
    let execution_start = Instant::now();
    let session = default_executor()
        .execute(execution_env, CSI_BREATHING_PROFILE_ELF)
        .context("RISC Zero profiling execution failed")?;
    let execution_seconds = execution_start.elapsed().as_secs_f64();
    let execution_user_cycles = session.cycles();
    let execution_segments = session
        .segments
        .iter()
        .map(|segment| SegmentOutput {
            po2: segment.po2,
            cycles: segment.cycles,
        })
        .collect();
    let execution_journal_decode_start = Instant::now();
    let execution_journal: ProfileJournal = session
        .journal
        .decode()
        .context("invalid profiling execution journal")?;
    let execution_journal_decode_seconds = execution_journal_decode_start.elapsed().as_secs_f64();
    drop(session);

    let proving_env_start = Instant::now();
    let proving_env = ExecutorEnv::builder().write(&request)?.build()?;
    let proving_env_build_seconds = proving_env_start.elapsed().as_secs_f64();
    let proving_start = Instant::now();
    let prove_info = default_prover()
        .prove(proving_env, CSI_BREATHING_PROFILE_ELF)
        .context("RISC Zero profiling proof failed")?;
    let proving_seconds = proving_start.elapsed().as_secs_f64();

    let verification_start = Instant::now();
    prove_info
        .receipt
        .verify(CSI_BREATHING_PROFILE_ID)
        .context("profiling receipt did not verify")?;
    let verification_seconds = verification_start.elapsed().as_secs_f64();
    let proof_journal_decode_start = Instant::now();
    let proof_journal: ProfileJournal = prove_info
        .receipt
        .journal
        .decode()
        .context("invalid profiling proof journal")?;
    let proof_journal_decode_seconds = proof_journal_decode_start.elapsed().as_secs_f64();
    if proof_journal != execution_journal {
        bail!("profiling execution and proof journals differ");
    }

    let receipt_serialize_start = Instant::now();
    let receipt_bytes = bincode::serialize(&prove_info.receipt)?.len();
    let receipt_serialize_seconds = receipt_serialize_start.elapsed().as_secs_f64();
    let stage_function_cycles = proof_journal
        .stage_cycles
        .iter()
        .map(|entry| entry.cycles)
        .sum::<u64>();
    let non_stage_profile_cycles = proof_journal
        .process_cycles
        .iter()
        .filter(|entry| {
            matches!(
                entry.process,
                ProfileProcess::GuestInputDeserialize | ProfileProcess::OutputChecksum
            )
        })
        .map(|entry| entry.inclusive_cycles)
        .sum::<u64>();
    let guest_profiled_cycles = stage_function_cycles.saturating_add(non_stage_profile_cycles);
    let guest_unattributed_cycles = execution_user_cycles.saturating_sub(guest_profiled_cycles);
    let mut output = ProfileOutput {
        stage,
        samples,
        subcarriers,
        input_elements,
        input_file_read_seconds: loaded.file_read_seconds,
        input_json_decode_seconds: loaded.json_decode_seconds,
        request_bytes,
        request_serialize_seconds,
        host_prepare_seconds,
        execution_env_build_seconds,
        execution_seconds,
        execution_user_cycles,
        execution_segments,
        execution_journal_decode_seconds,
        proving_env_build_seconds,
        proving_seconds,
        verification_seconds,
        proof_journal_decode_seconds,
        receipt_bytes,
        receipt_serialize_seconds,
        guest_profiled_cycles,
        guest_unattributed_cycles,
        proof_stats: ProofStatsOutput {
            segments: prove_info.stats.segments,
            total_cycles: prove_info.stats.total_cycles,
            user_cycles: prove_info.stats.user_cycles,
            paging_cycles: prove_info.stats.paging_cycles,
            reserved_cycles: prove_info.stats.reserved_cycles,
        },
        journal: proof_journal,
        method: "risc0_stage_profile_v1",
        output_json_serialize_seconds: 0.0,
        total_host_seconds: total_start.elapsed().as_secs_f64(),
    };
    let output_serialize_start = Instant::now();
    let _ = serde_json::to_string(&output)?;
    output.output_json_serialize_seconds = output_serialize_start.elapsed().as_secs_f64();
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}
