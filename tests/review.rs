use std::{
    io::Write,
    process::{Command, Stdio},
};
fn run(args: &[&str], input: &str) -> std::process::Output {
    let mut c = Command::new(env!("CARGO_BIN_EXE_nobotrs"));
    for (key, _) in std::env::vars().filter(|(k, _)| k.starts_with("NOBOTRS_")) {
        c.env_remove(key);
    }
    let mut child = c
        .args(args)
        .env("XDG_CONFIG_HOME", "/tmp/nobotrs-review-no-config")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(input.as_bytes())
        .unwrap();
    child.wait_with_output().unwrap()
}
fn json(args: &[&str], input: &str) -> serde_json::Value {
    let o = run(args, input);
    assert!(o.status.success(), "{}", String::from_utf8_lossy(&o.stderr));
    serde_json::from_slice(&o.stdout).unwrap()
}
#[test]
fn ranking_counts_and_display_limit_are_independent() {
    let text =
        "We must delve into this. Studies show it matters. It's not just a tool, it's a shift.";
    let all = json(
        &["review", "-", "--language", "en", "--format", "json"],
        text,
    );
    assert_eq!(all["findings"][0]["rule_id"], "studies-show");
    for limit in ["0", "1"] {
        let v = json(
            &[
                "review",
                "-",
                "--language",
                "en",
                "--format",
                "json",
                "--display-limit",
                limit,
            ],
            text,
        );
        assert_eq!(
            v["findings"].as_array().unwrap().len(),
            limit.parse::<usize>().unwrap()
        );
        assert_eq!(v["leverage_counts"], all["leverage_counts"]);
        assert_eq!(v["checklist"], all["checklist"]);
        assert_eq!(v["total_findings"], all["total_findings"]);
        if limit == "1" {
            assert_eq!(v["findings"][0]["rule_id"], "studies-show");
        }
    }
}
#[test]
fn empty_and_code_only_are_not_applicable() {
    for input in ["", "```\nIn conclusion. **Bold:**\n```\n"] {
        let v = json(&["review", "-", "--markdown", "--format", "json"], input);
        assert!(v["findings"].as_array().unwrap().is_empty());
        assert!(v["checklist"]
            .as_array()
            .unwrap()
            .iter()
            .all(|c| c["status"] == "not_applicable"));
    }
    assert!(
        json(&["review", "-", "--format", "json"], "code")["prose_words"]
            .as_u64()
            .unwrap()
            > 0
    );
}
#[test]
fn suppressions_precede_ranking_and_overlap_selection() {
    let v = json(
        &[
            "review",
            "-",
            "--markdown",
            "--language",
            "en",
            "--format",
            "json",
        ],
        "<!-- nobotrs-ignore-next-line delve -->\nWe delve.\n\nStudies show robust gains.\n",
    );
    let f = v["findings"].as_array().unwrap();
    let last = f.last().unwrap();
    assert_eq!(last["suppressed"], true);
    assert_eq!(last["location"]["line"], 2);
    assert_eq!(last["location"]["column"], 4);
    for ignore in [None, Some("not-just-x-but-y")] {
        let mut args = vec!["review", "-", "--language", "en", "--format", "json"];
        if let Some(rule) = ignore {
            args.extend(["--ignore-rule", rule]);
        }
        let v = json(&args, "It's not just a tool, it's a shift.");
        let active: Vec<_> = v["findings"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|f| {
                f["suppressed"] == false
                    && ["not-just-x-but-y", "structure.negative-parallelism"]
                        .contains(&f["rule_id"].as_str().unwrap())
            })
            .collect();
        assert_eq!(active.len(), 1);
        assert_eq!(
            active[0]["rule_id"],
            if ignore.is_none() {
                "not-just-x-but-y"
            } else {
                "structure.negative-parallelism"
            }
        );
    }
}
#[test]
fn incomplete_disabled_and_unknown_checks_are_visible() {
    assert_eq!(
        run(&["review", "-", "--timeout-ms", "0"], "We delve.")
            .status
            .code(),
        Some(2)
    );
    assert_eq!(
        run(
            &["review", "-", "--language", "en", "--max-candidates", "1"],
            "Certainly! Still short."
        )
        .status
        .code(),
        Some(2)
    );
    assert_eq!(
        run(&["review", "-", "--max-bytes", "2"], "long input")
            .status
            .code(),
        Some(2)
    );
    let v = json(
        &["review", "-", "--format", "json"],
        "In conclusion, budgets matter.",
    );
    assert_eq!(
        v["checklist"]
            .as_array()
            .unwrap()
            .iter()
            .find(|c| c["id"] == "no-summary-close")
            .unwrap()["status"],
        "unknown"
    );
    let path = std::env::temp_dir().join(format!(
        "nobotrs-review-disabled-{}.json",
        std::process::id()
    ));
    std::fs::write(&path, r#"{"enabled_backends":["punctuation"]}"#).unwrap();
    let v = json(
        &[
            "review",
            "-",
            "--language",
            "en",
            "--format",
            "json",
            "--config",
            path.to_str().unwrap(),
        ],
        "In conclusion, budgets matter.",
    );
    assert!(v["checks"]
        .as_array()
        .unwrap()
        .iter()
        .any(|c| c["backend"] == "structure" && c["status"] == "skipped"));
    std::fs::remove_file(path).unwrap();
}
#[test]
fn external_flags_and_configuration_are_rejected() {
    for flag in ["--gptzero", "--openrouter-judge"] {
        assert_eq!(run(&["review", "-", flag], "text").status.code(), Some(2));
    }
    for key in ["gptzero", "openrouter_judge"] {
        let p =
            std::env::temp_dir().join(format!("nobotrs-review-{key}-{}.json", std::process::id()));
        std::fs::write(&p, format!("{{\"{key}\":true}}")).unwrap();
        let o = run(&["review", "-", "--config", p.to_str().unwrap()], "text");
        assert_eq!(o.status.code(), Some(2));
        assert!(o.stdout.is_empty());
        std::fs::remove_file(p).unwrap();
    }
    assert_eq!(
        run(&["review", "-", "--format", "sarif"], "text")
            .status
            .code(),
        Some(2)
    );
}
#[test]
fn document_finding_is_unlocated_and_unique() {
    let text = ["This sentence has six words total."; 31].join(" ");
    let v = json(
        &[
            "review",
            "-",
            "--language",
            "en",
            "--format",
            "json",
            "--display-limit",
            "1000",
        ],
        &text,
    );
    let docs = v["document"].as_array().unwrap();
    assert_eq!(
        docs.iter()
            .filter(|f| f["rule_id"] == "statistics.burstiness")
            .count(),
        1
    );
    assert!(docs
        .iter()
        .all(|f| f["location"].is_null() && f["message"].is_string()));
}
#[test]
fn bibb_review_snapshot() {
    let input = include_str!("../evaluation/fixtures/bibb-fy27.txt");
    let v = json(
        &["review", "-", "--language", "en", "--format", "json"],
        input,
    );
    let f = v["findings"].as_array().unwrap();
    let gerund = f
        .iter()
        .position(|f| f["rule_id"] == "structure.coordinated-series")
        .unwrap();
    let dash = f
        .iter()
        .position(|f| f["rule_id"] == "punctuation.em-dash-density")
        .unwrap();
    assert!(gerund < dash);
    let dashes: Vec<_> = f
        .iter()
        .filter(|f| f["rule_id"] == "punctuation.em-dash-density")
        .collect();
    assert_eq!(dashes.len(), 9);
    assert!(dashes.iter().all(|f| f["context"] == "list_separator"));
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/review/bibb-fy27.json");
    if std::env::var_os("NOBOTRS_UPDATE_SNAPSHOTS").is_some() {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, serde_json::to_string_pretty(&v).unwrap() + "\n").unwrap();
    }
    assert_eq!(
        v,
        serde_json::from_str::<serde_json::Value>(&std::fs::read_to_string(path).unwrap()).unwrap()
    );
}

#[test]
fn suppressed_region_without_matching_candidate_is_unknown() {
    let v = json(
        &[
            "review",
            "-",
            "--markdown",
            "--language",
            "en",
            "--format",
            "json",
        ],
        "<!-- nobotrs-ignore-file structure.summary-close -->\nThe board meets Friday.\n",
    );
    assert_eq!(
        v["checklist"]
            .as_array()
            .unwrap()
            .iter()
            .find(|c| c["id"] == "no-summary-close")
            .unwrap()["status"],
        "unknown"
    );
}
