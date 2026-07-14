use std::{env, fs, path::PathBuf};

use anyhow::{Context, Result, bail};
use base64::{Engine as _, engine::general_purpose::STANDARD};
use csi_zkvm_core::{PipelineInput, PipelineJournal};
use csi_zkvm_methods::{CSI_BREATHING_GUEST_ELF, CSI_BREATHING_GUEST_ID};
use risc0_zkvm::{ExecutorEnv, default_prover};
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
}

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let command = args.next().unwrap_or_default();
    let input_path = args.next().map(PathBuf::from);
    if command != "prove" || input_path.is_none() || args.next().is_some() {
        bail!("usage: csi-zkvm-host prove <pipeline-input.json>");
    }

    let input_bytes =
        fs::read(input_path.expect("checked above")).context("failed to read input")?;
    let input: PipelineInput =
        serde_json::from_slice(&input_bytes).context("invalid pipeline input")?;
    let executor_env = ExecutorEnv::builder().write(&input)?.build()?;
    let receipt = default_prover()
        .prove(executor_env, CSI_BREATHING_GUEST_ELF)
        .context("RISC Zero proof generation failed")?
        .receipt;
    receipt
        .verify(CSI_BREATHING_GUEST_ID)
        .context("locally generated receipt did not verify")?;
    let journal: PipelineJournal = receipt.journal.decode().context("invalid guest journal")?;
    let encoded_receipt = STANDARD.encode(bincode::serialize(&receipt)?);
    let output = ProverOutput {
        is_normal: journal.is_normal,
        is_valid: true,
        receipt: encoded_receipt,
        journal,
        method: "risc0_5_1_fixed_v1",
    };
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}
