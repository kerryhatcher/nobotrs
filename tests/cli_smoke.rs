use std::{
    io::Write,
    process::{Command, Stdio},
};
fn cli(args: &[&str], input: &[u8]) -> std::process::Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .args(args)
        .env("XDG_CONFIG_HOME", "/tmp/nobotrs-test-no-config")
        .env_remove("NOBOTRS_CONFIG")
        .env_remove("NOBOTRS_QUORUM")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(input).unwrap();
    child.wait_with_output().unwrap()
}
#[test]
fn full_ai_writing_guide_is_available_as_markdown_and_json() {
    let guide = include_str!("../docs/ai-writing-guide.md");
    let markdown = cli(&["ai-writing-guide", "--quorum", "0"], b"");
    assert!(markdown.status.success());
    assert_eq!(markdown.stdout, guide.as_bytes());
    assert!(markdown.stderr.is_empty());

    let json = cli(&["ai-writing-guide", "--format", "json"], b"");
    assert!(json.status.success());
    let report: serde_json::Value = serde_json::from_slice(&json.stdout).unwrap();
    assert_eq!(report["schema_version"], "1.0.0");
    assert_eq!(report["guide"], guide);

    let sarif = cli(&["ai-writing-guide", "--format", "sarif"], b"");
    assert_eq!(sarif.status.code(), Some(2));
    assert!(sarif.stdout.is_empty());
}

#[test]
fn stdin_is_read_and_findings_affect_status() {
    let o = cli(&["lint", "-", "--format", "json"], b"delve leverage");
    assert_eq!(o.status.code(), Some(1));
    let r: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(r["effective_finding_count"], 2);
    assert_eq!(r["schema_version"], "1.0.0");
    assert!(o.stderr.is_empty());
    let o = cli(&["detect", "-", "--format", "json"], b"");
    assert_eq!(o.status.code(), Some(3));
    let r: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(r["verdict"], "inconclusive");
}
#[test]
fn missing_invalid_and_oversized_inputs_fail() {
    for (args, input) in [
        (
            vec!["detect", "/path/does/not/exist", "--format", "json"],
            vec![],
        ),
        (vec!["detect", "-"], vec![0xff]),
        (
            vec!["detect", "-", "--max-bytes", "2"],
            b"long input".to_vec(),
        ),
    ] {
        let o = cli(&args, &input);
        assert_eq!(o.status.code(), Some(2));
    }
    assert_eq!(
        cli(&["config", "--quorum", "0"], b"").status.code(),
        Some(2)
    );
}
#[test]
fn sarif_declares_unicode_columns_and_severity_levels() {
    let o = cli(
        &["lint", "-", "--markdown", "--format", "sarif"],
        "😀 delve\n<!-- nobotrs-ignore-next-line leverage -->\nleverage\n".as_bytes(),
    );
    let report: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    let run = &report["runs"][0];
    assert_eq!(run["columnKind"], "unicodeCodePoints");
    let delve = run["results"]
        .as_array()
        .unwrap()
        .iter()
        .find(|result| result["ruleId"] == "delve")
        .unwrap();
    assert_eq!(delve["level"], "warning");
    assert_eq!(
        delve["locations"][0]["physicalLocation"]["region"],
        serde_json::json!({"startLine": 1, "endLine": 1, "startColumn": 3, "endColumn": 8})
    );
    let rules = run["tool"]["driver"]["rules"].as_array().unwrap();
    let rule = rules.iter().find(|rule| rule["id"] == "delve").unwrap();
    assert_eq!(delve["level"], rule["defaultConfiguration"]["level"]);
}

#[test]
fn markdown_hint_and_display_limit_work_through_executable() {
    let o = cli(
        &["lint", "-", "--markdown", "--format", "json"],
        b"```\ndelve leverage\n```\n",
    );
    assert_eq!(o.status.code(), Some(3));
    let o = cli(
        &["lint", "-", "--display-limit", "0", "--format", "json"],
        b"delve leverage",
    );
    assert_eq!(o.status.code(), Some(1));
    let r: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(r["omitted_findings"], 2);
}

#[test]
fn config_precedence_errors_and_mixed_scan_are_real() {
    use std::{fs, path::PathBuf};
    let root = PathBuf::from(format!("/tmp/nobotrs-cli-tests-{}", std::process::id()));
    fs::create_dir_all(root.join("target")).unwrap();
    let config = root.join("settings.json");
    fs::write(&config, "{\"quorum\":1}").unwrap();
    let o = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .args([
            "config",
            "--config",
            config.to_str().unwrap(),
            "--quorum",
            "3",
        ])
        .env("NOBOTRS_QUORUM", "2")
        .output()
        .unwrap();
    assert!(o.status.success());
    let r: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(r["configuration"]["settings"]["quorum"], 3);
    assert_eq!(r["configuration"]["origins"]["quorum"], "cli");
    fs::write(root.join("a.txt"), "quiet plain prose").unwrap();
    fs::write(root.join("b.txt"), [0xff]).unwrap();
    fs::write(root.join("target/ignored.md"), "delve leverage").unwrap();
    let o = cli(&["scan", root.to_str().unwrap(), "--format", "json"], b"");
    assert_eq!(o.status.code(), Some(2));
    let r: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(r["reports"].as_array().unwrap().len(), 1);
    assert_eq!(r["errors"].as_array().unwrap().len(), 1);
    let o = cli(
        &[
            "lint",
            root.join("a.txt").to_str().unwrap(),
            root.join("b.txt").to_str().unwrap(),
            "--format",
            "json",
        ],
        b"",
    );
    assert_eq!(o.status.code(), Some(2));
    fs::remove_dir_all(root).unwrap();
}
#[test]
fn input_cap_retains_partial_findings() {
    let o = cli(
        &["lint", "-", "--max-bytes", "6", "--format", "json"],
        b"delve more text",
    );
    assert_eq!(o.status.code(), Some(2));
    let r: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(r["complete"], false);
    assert_eq!(r["effective_finding_count"], 1);
}
