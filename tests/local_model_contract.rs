use serde_json::Value;
use std::{
    io::Write,
    path::PathBuf,
    process::{Command, Stdio},
    sync::OnceLock,
};

fn run(args: &[&str], input: &str) -> (i32, Value) {
    static CONFIG: OnceLock<PathBuf> = OnceLock::new();
    let config = CONFIG.get_or_init(|| {
        let path = PathBuf::from(env!("CARGO_TARGET_TMPDIR"))
            .join(format!("local-model-config-{}.json", std::process::id()));
        std::fs::write(&path, "{}").unwrap();
        path
    });
    let mut command = Command::new(env!("CARGO_BIN_EXE_nobotrs"));
    for (name, _) in std::env::vars_os() {
        if name.to_string_lossy().starts_with("NOBOTRS_") {
            command.env_remove(name);
        }
    }
    let mut child = command
        .args(args)
        .arg("--config")
        .arg(config)
        .args(["--format", "json"])
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
    let output = child.wait_with_output().unwrap();
    let report = serde_json::from_slice(&output.stdout).unwrap_or_else(|error| {
        panic!(
            "JSON report: {error}\nstderr: {}",
            String::from_utf8_lossy(&output.stderr)
        )
    });
    (output.status.code().unwrap(), report)
}

#[test]
fn config_reports_unavailable_requested_backends_without_loading_models() {
    let (code, report) = run(&["config", "--models", "desklib,conpara,detectorscope"], "");
    assert_eq!(code, 0);
    assert_eq!(report["schema_version"], "1.0.0");
    let statuses = report["models"].as_array().unwrap();
    for id in ["desklib", "conpara", "detectorscope"] {
        let status = statuses
            .iter()
            .find(|status| status["backend"] == id)
            .unwrap();
        assert_eq!(status["enabled"], true);
        assert_eq!(status["artifacts"], "not_configured");
        assert_ne!(status["availability"], "ready");
    }
}

#[test]
fn requested_unavailable_models_preserve_heuristic_results() {
    let text = "The project started in June. Staff wrote a short account of the move. They recorded the costs, answered questions from residents, and published the result.";
    let (_, baseline) = run(&["analyze", "-", "--language", "en"], text);
    let (code, report) = run(
        &[
            "analyze",
            "-",
            "--language",
            "en",
            "--models",
            "desklib,conpara",
        ],
        text,
    );
    assert_eq!(code, 2);
    assert_eq!(report["complete"], false);
    assert_eq!(report["analyzed_coverage"], baseline["analyzed_coverage"]);
    for key in [
        "verdict",
        "families",
        "effective_finding_count",
        "actionable_finding_count",
    ] {
        assert_eq!(report[key], baseline[key], "{key}");
    }
    let backends = report["backends"].as_array().unwrap();
    for baseline_backend in baseline["backends"].as_array().unwrap() {
        assert!(backends.contains(baseline_backend));
    }
    for id in ["desklib", "conpara"] {
        let backend = backends
            .iter()
            .find(|backend| backend["backend"] == id)
            .unwrap();
        assert_eq!(backend["outcome"]["status"], "failed");
    }
}

#[test]
fn scan_keeps_path_order_and_reports_incomplete_model_requests() {
    let args = ["scan", "tests/fixtures/evaluation", "--language", "en"];
    let (_, baseline) = run(&args, "");
    let (code, result) = run(&[args.as_slice(), &["--models", "desklib"]].concat(), "");
    assert_eq!(code, 2);
    assert_eq!(result["exit_code"], 2);
    assert_eq!(result["errors"], serde_json::json!([]));
    let reports = result["reports"].as_array().unwrap();
    let baseline_reports = baseline["reports"].as_array().unwrap();
    assert_eq!(reports.len(), baseline_reports.len());
    assert!(reports.len() > 1);
    assert!(reports
        .windows(2)
        .all(|pair| { pair[0]["path"].as_str().unwrap() < pair[1]["path"].as_str().unwrap() }));
    for (report, original) in reports.iter().zip(baseline_reports) {
        for key in ["path", "verdict", "families", "effective_finding_count"] {
            assert_eq!(report[key], original[key], "{key}");
        }
    }
}
