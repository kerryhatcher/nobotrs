use serde_json::Value;
use std::process::Command;
fn run(experiment: &str) -> (i32, Vec<u8>) {
    let out = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .args([
            "analyze",
            "evaluation/fixtures/bibb-fy27.txt",
            "--language",
            "en",
            "--format",
            "json",
        ])
        .env("NOBOTRS_EXPERIMENT", experiment)
        .output()
        .unwrap();
    (out.status.code().unwrap(), out.stdout)
}
fn report(id: &str) -> Value {
    serde_json::from_slice(&run(id).1).unwrap()
}
fn score<'a>(v: &'a Value, name: &str) -> &'a Value {
    &v["backends"]
        .as_array()
        .unwrap()
        .iter()
        .find(|v| v["backend"] == name)
        .unwrap()["outcome"]["details"]
}
#[test]
fn opt_in_does_not_change_baseline() {
    let old = report("");
    assert!(old["settings"].get("experiment").is_none());
    assert_eq!(
        score(&old, "punctuation")["metrics"]["em_dash_count"]["value"],
        9.0
    );
    let new = report("punctuation-skip-list-separators,burstiness-units,structure-votes");
    assert_eq!(
        score(&new, "punctuation")["metrics"]["em_dash_count"]["value"],
        0.0
    );
    assert_ne!(
        score(&old, "burstiness")["metrics"]["sentence_length_cv"],
        score(&new, "burstiness")["metrics"]["sentence_length_cv"]
    );
    assert_eq!(score(&new, "structure")["voting_eligible"], true);
    assert!(new["metric_contract"]
        .as_str()
        .unwrap()
        .ends_with("+experimental"));
    assert_eq!(run("bogus").0, 2);
}
