use std::{
    io::Write,
    process::{Command, Stdio},
};
fn run(args: &[&str], input: &str) -> std::process::Output {
    let mut c = Command::new(env!("CARGO_BIN_EXE_nobotrs"));
    for (k, _) in std::env::vars().filter(|(k, _)| k.starts_with("NOBOTRS_")) {
        c.env_remove(k);
    }
    let mut c = c
        .args(args)
        .env("XDG_CONFIG_HOME", "/tmp/nobotrs-guide-no-config")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    c.stdin.take().unwrap().write_all(input.as_bytes()).unwrap();
    c.wait_with_output().unwrap()
}
#[test]
fn guide_keeps_legacy_json_and_adds_canonical_data() {
    let o = run(&["guide", "--format", "json"], "");
    assert!(o.status.success());
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(v["guide"], include_str!("../docs/writing-guide.md"));
    assert_eq!(v["guidance_version"], "2026.11.21");
    let human = run(&["guide"], "");
    assert_eq!(
        String::from_utf8(human.stdout).unwrap().trim_end(),
        v["brief"].as_str().unwrap().trim_end()
    );
    let brief = v["brief"].as_str().unwrap();
    let headings = [
        "## Before you write",
        "## While you write",
        "## Revising an existing draft",
        "## When to stop",
        "## Reader-first and search",
        "## Never do this",
    ];
    assert!(headings
        .map(|h| brief.find(h).unwrap())
        .windows(2)
        .all(|w| w[0] < w[1]));
    assert!(v["entries"]
        .as_array()
        .unwrap()
        .iter()
        .all(|e| e["leverage"].is_number()));
}
#[test]
fn lint_metadata_is_additive_and_sarif_has_no_guidance() {
    let o = run(
        &["lint", "-", "--format", "json"],
        "Studies show we must delve.",
    );
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    let ev = v["backends"]
        .as_array()
        .unwrap()
        .iter()
        .find(|b| b["backend"] == "vocabulary")
        .unwrap()["outcome"]["details"]["evidence"]
        .as_array()
        .unwrap();
    assert!(ev.iter().any(|e| e["rule_id"] == "studies-show"
        && e["guidance_id"] == "content.vague-attribution"
        && e["leverage"] == 1));
    let sarif = run(
        &["lint", "-", "--format", "sarif"],
        "Studies show we must delve.",
    );
    assert!(!String::from_utf8_lossy(&sarif.stdout).contains("guidance_id"));
}
#[test]
fn operational_guidance_removes_fabrication_advice() {
    let g = include_str!("../docs/ai-writing-guide.md");
    let practical =
        &g[g.find("## Practical instructions").unwrap()..g.find("## Detector advances").unwrap()];
    for bad in [
        "Henderson's place",
        "Set temperature to maximum",
        "persona with lived experience",
        "avoid curly quotation marks",
    ] {
        assert!(!practical.contains(bad));
    }
}

#[test]
fn sarif_bytes_match_pre_guidance_contract() {
    let o = run(
        &["lint", "-", "--format", "sarif", "--language", "en"],
        "Studies show we must delve into robust solutions.\n",
    );
    assert_eq!(o.status.code(), Some(1));
    assert_eq!(
        o.stdout,
        include_bytes!("fixtures/review/legacy-lint-sarif.json")
    );
}
