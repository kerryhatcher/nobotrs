use serde_json::Value;
use std::{
    io::Write,
    process::{Command, Stdio},
    sync::atomic::{AtomicUsize, Ordering},
};
static COUNTER: AtomicUsize = AtomicUsize::new(0);
fn compare(before: &str, after: &str, args: &[&str]) -> (i32, Value) {
    let path = std::env::temp_dir().join(format!(
        "nobotrs-compare-{}-{}.md",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    ));
    std::fs::write(&path, after).unwrap();
    let mut c = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .args(["compare", "-"])
        .arg(&path)
        .args(["--markdown", "--language", "en", "--format", "json"])
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    c.stdin
        .take()
        .unwrap()
        .write_all(before.as_bytes())
        .unwrap();
    let out = c.wait_with_output().unwrap();
    std::fs::remove_file(path).unwrap();
    (
        out.status.code().unwrap(),
        serde_json::from_slice(&out.stdout).unwrap(),
    )
}
#[test]
fn removed_values_require_author_confirmation() {
    let a = "The report lists $8 million.";
    let b = "The report lists the amount.";
    let (code, r) = compare(a, b, &[]);
    assert_eq!(code, 1);
    assert_eq!(r["missing"][0]["kind"], "number");
    let (code, r) = compare(a, b, &["--accept-missing", "number=$8 million"]);
    assert_eq!(code, 0);
    assert_eq!(r["accepted_missing"].as_array().unwrap().len(), 1);
}
#[test]
fn equivalent_money_and_moved_paragraphs() {
    let (code, r) = compare(
        "Parks FY27 budget: $8 million\n\nWait.",
        "Wait.\n\nParks FY27 budget: $8M",
        &[],
    );
    assert_eq!(code, 0);
    assert!(r["missing"].as_array().unwrap().is_empty());
}
#[test]
fn swapped_attributions_and_links() {
    let (code, r) = compare(
        "Parks budget: $4M\n\nLibrary budget: $8M\n\n[Source](old.md)",
        "Parks budget: $8M\n\nLibrary budget: $4M\n\n[Source](new.md)",
        &[],
    );
    assert_eq!(code, 1);
    let missing = r["missing"].as_array().unwrap();
    assert!(missing.iter().any(|i| i["kind"] == "link"));
    assert_eq!(
        missing
            .iter()
            .filter(|i| i["kind"] == "anchored_claim")
            .count(),
        2
    );
}
#[test]
fn fenced_code_and_qualifications() {
    let (code, r) = compare(
        "The board may act.\n\n```sh\ncargo check\n```",
        "The board will act.",
        &[],
    );
    assert_eq!(code, 1);
    assert!(r["missing"]
        .as_array()
        .unwrap()
        .iter()
        .any(|i| i["kind"] == "qualifier"));
}

#[test]
fn punctuation_after_amount_is_not_part_of_its_value() {
    let (exit, report) = compare(
        "The grant was $8, and the fee was $1,200.50.",
        "The fee was $1200.50 and the grant was $8.",
        &[],
    );
    assert_eq!(exit, 0);
    assert!(!report["missing"]
        .as_array()
        .unwrap()
        .iter()
        .any(|i| i["kind"] == "number"));
}
