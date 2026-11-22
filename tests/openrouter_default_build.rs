//! Without the `api-clients` feature, `--openrouter-judge` must fail loudly and never send anything.
#![cfg(not(feature = "api-clients"))]

use std::process::Command;

#[test]
fn openrouter_flag_is_rejected_when_feature_is_absent() {
    let sample =
        std::path::PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join("openrouter_default_sample.txt");
    std::fs::write(&sample, "A short sample sentence for the default build.\n").unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .args(["--openrouter-judge", "detect"])
        .arg(&sample)
        .env("OPENROUTER_API_KEY", "or-test-key-do-not-leak-4242")
        .env("NOBOTRS_OPENROUTER_BASE_URL", "http://127.0.0.1:9/api/v1")
        .output()
        .expect("run binary");
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(!out.status.success(), "must not succeed silently");
    assert!(stderr.contains("api-clients"), "{stderr}");
    assert!(!stderr.contains("or-test-key-do-not-leak-4242"));
}
