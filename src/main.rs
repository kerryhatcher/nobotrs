// src/main.rs
mod availability;
mod deadline;
mod error;
mod cli;

use clap::Parser;
use cli::{Cli, Command};

fn main() {
    let cli = Cli::parse();
    let code = match cli.command {
        Command::Detect { path } => cli::detect::run(&path),
        Command::Lint { path } => cli::lint::run(&path),
        Command::Scan { dir } => cli::scan::run(&dir),
        Command::Config => cli::config::run(),
    };
    std::process::exit(code);
}
