#![no_main]
#![no_std]

#[path = "../profile_support.rs"]
mod profile_support;

use risc0_zkvm::guest::env;

risc0_zkvm::guest::entry!(main);

fn main() {
    profile_support::run_combined();
}
