//! Without the `api-clients` feature, `--gptzero` must fail loudly and never send anything.
#![cfg(not(feature = "api-clients"))]

use std::process::Command;

#[test]
fn gptzero_flag_is_rejected_when_feature_is_absent() {
    let sample =
        std::path::PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join("gptzero_default_sample.txt");
    std::fs::write(&sample, "A short sample sentence for the default build.\n").unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .args(["--gptzero", "detect"])
        .arg(&sample)
        .env("GPTZERO_API_KEY", "test-key-do-not-leak-7731")
        .env("NOBOTRS_GPTZERO_BASE_URL", "http://127.0.0.1:9")
        .output()
        .expect("run binary");
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(!out.status.success(), "must not succeed silently");
    assert!(stderr.contains("api-clients"), "{stderr}");
    assert!(!stderr.contains("test-key-do-not-leak-7731"));
}

#[test]
fn default_build_detect_is_unchanged_without_flag() {
    let sample =
        std::path::PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join("gptzero_default_plain.txt");
    std::fs::write(&sample, "A short sample sentence for the default build.\n").unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .args(["--format", "json", "detect"])
        .arg(&sample)
        .output()
        .expect("run binary");
    let value: serde_json::Value = serde_json::from_slice(&out.stdout).expect("json");
    let report = match value {
        serde_json::Value::Array(items) => items.into_iter().next().unwrap(),
        other => other,
    };
    assert!(
        report.get("external").is_none(),
        "external must be absent by default"
    );
}
