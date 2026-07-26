// tests/cli_smoke.rs
use std::process::Command;

#[test]
fn detect_dash_reads_stdin_and_runs() {
    let output = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .arg("detect")
        .arg("-")
        .env("CI", "1")
        .output()
        .expect("binary should run");
    // Stubbed in this task: only asserts the binary exists and exits with a
    // code the CLI actually defines (0-3), not 101 (panic) or 127 (not found).
    let code = output.status.code().expect("should exit with a code");
    assert!((0..=3).contains(&code), "unexpected exit code {code}");
}
