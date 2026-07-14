#![no_main]
#![no_std]

use csi_zkvm_core::{PipelineInput, run_pipeline};
use risc0_zkvm::guest::env;

risc0_zkvm::guest::entry!(main);

fn main() {
    let input: PipelineInput = env::read();
    let journal = run_pipeline(&input).expect("5-1 fixed-point pipeline rejected its input");
    env::commit(&journal);
}

