// src/cli/mod.rs
use clap::{Parser, Subcommand};

pub mod config;
pub mod detect;
pub mod lint;
pub mod scan;

#[derive(Parser)]
#[command(name = "nobotrs", about = "Detects AI-generated text and lints prose for AI-writing tells")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Subcommand)]
pub enum Command {
    /// Score a file or stdin ("-") for a quorum ensemble verdict.
    Detect { path: String },
    /// Line-anchored tells report: every backend's evidence, unfiltered by quorum.
    Lint { path: String },
    /// Batch lint across a directory.
    Scan { dir: String },
    /// Manage API keys, model downloads, enabled backends, availability status.
    Config,
}
