use std::{
    io::Write,
    process::{Command, Stdio},
};
fn check(text: &str, markdown: bool) -> (i32, serde_json::Value) {
    let mut c = Command::new(env!("CARGO_BIN_EXE_nobotrs"));
    c.args(["facts", "check", "-", "--format", "json"]);
    if markdown {
        c.arg("--markdown");
    }
    let mut child = c
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(text.as_bytes())
        .unwrap();
    let out = child.wait_with_output().unwrap();
    (
        out.status.code().unwrap(),
        serde_json::from_slice(&out.stdout).unwrap(),
    )
}
#[test]
fn normalized_amounts_and_periods() {
    let (code, r) = check(
        "Parks FY27: $8 million\nParks FY27: $8,000,000\nParks FY26: $7 million",
        false,
    );
    assert_eq!(code, 0);
    assert_eq!(r["groups"][1]["status"], "compatible");
    assert_eq!(r["groups"][1]["mentions"][1]["line"], 2);
}
#[test]
fn table_conflict_retains_coordinates() {
    let (code, r) = check(
        "| Agency | FY27 budget |\n|---|---|\n| Parks | $4 million |\n| Parks | $8 million |\n",
        true,
    );
    assert_eq!(code, 1);
    let g = &r["groups"][0];
    assert_eq!(g["label"], "parks fy27 budget");
    assert_eq!(g["mentions"][1]["line"], 4);
}
#[test]
fn ignores_code_and_abstains_on_unanchored_prose() {
    let (code, r) = check(
        "A city spent $8 million.\n\n```text\nParks FY27: $1 million\n```",
        true,
    );
    assert_eq!(code, 3);
    assert_eq!(r["facts_extracted"], 0);
}

#[test]
fn source_reference_and_directory_keep_years_separate() {
    let root = std::env::temp_dir().join(format!("nobotrs-facts-test-{}", std::process::id()));
    let docs = root.join("docs");
    std::fs::create_dir_all(&docs).unwrap();
    let source = root.join("source.txt");
    std::fs::write(
        &source,
        "Parks FY27 budget: $8M\nLibrary FY27 budget: $4M\n",
    )
    .unwrap();
    std::fs::write(
        docs.join("draft.md"),
        "Parks FY27 budget is $8 million.\n\nParks FY26 budget was $7 million.\n",
    )
    .unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .args(["facts", "check"])
        .arg(&docs)
        .arg("--reference")
        .arg(source)
        .args(["--format", "json"])
        .output()
        .unwrap();
    std::fs::remove_dir_all(root).unwrap();
    assert_eq!(out.status.code(), Some(1));
    let value: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    let groups = value["groups"].as_array().unwrap();
    assert!(groups
        .iter()
        .any(|g| g["label"] == "parks fy27 budget" && g["status"] == "compatible"));
    assert!(groups
        .iter()
        .any(|g| g["label"] == "library fy27 budget" && g["status"] == "missing_expected"));
}

#[test]
fn dates_and_approximation_keep_scope() {
    let (code,r)=check("Start date: 2024-02-29\nStart date: 2024-02-29\nBad date: 2025-02-29\nReserve: about $2M\nReserve: $2.2M",false);
    assert_eq!(code, 0);
    assert_eq!(r["facts_extracted"], 4);
    assert!(r["groups"]
        .as_array()
        .unwrap()
        .iter()
        .all(|g| g["status"] != "conflict"));
}

#[test]
fn adjacent_assertions_keep_decimal_values_and_source_columns() {
    let text = "Café budget is $2.5M. Café budget is $3M.";
    for markdown in [false, true] {
        let (code, report) = check(text, markdown);
        assert_eq!(code, 1);
        let second = &report["groups"][0]["mentions"][1];
        let offset = text.find("$3M").unwrap();
        assert_eq!(second["byte_offset"], offset);
        assert_eq!(second["column"], text[..offset].chars().count() + 1);
    }
}

#[test]
fn pronouns_and_possible_short_names_require_resolution() {
    let (code, result) = check("It is $8M. It is $4M.\nBibb FY27 budget: about $8M\nBibb County Schools FY27 budget: about $9M", false);
    assert_eq!(code, 3);
    let groups = result["groups"].as_array().unwrap();
    assert!(groups
        .iter()
        .any(|g| g["label"] == "it" && g["status"] == "ambiguous"));
    let short = groups
        .iter()
        .find(|g| g["label"] == "bibb fy27 budget")
        .unwrap();
    assert_eq!(short["status"], "ambiguous");
    assert_eq!(short["context"]["qualifier"], "approximate");
    assert_eq!(short["context"]["attribute"], "budget");
    assert_eq!(
        short["possible_entity_expansions"][0],
        "bibb county schools"
    );
}
