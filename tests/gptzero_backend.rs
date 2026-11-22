//! GPTZero client tests against a local mock server. No test contacts the real API.
#![cfg(feature = "api-clients")]

use nobotrs::config::Settings;
use nobotrs::external::gptzero::client::{ClientError, DetectResponse, GptZeroClient};
use nobotrs::external::gptzero::compare;
use nobotrs::external::ExternalStatus;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread::{self, JoinHandle};
use std::time::Duration;

const AI_FIXTURE: &str = include_str!("fixtures/gptzero/predict_text_ai.json");
const TEST_KEY: &str = "test-key-do-not-leak-7731";

/// Serves exactly one HTTP request and returns the raw request text it received.
fn serve_once(status: &str, body: &str) -> (String, JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock server");
    let base = format!("http://{}", listener.local_addr().unwrap());
    let response = format!(
        "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("accept");
        stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut buf = Vec::new();
        let mut chunk = [0u8; 4096];
        loop {
            let n = stream.read(&mut chunk).unwrap_or(0);
            if n == 0 {
                break;
            }
            buf.extend_from_slice(&chunk[..n]);
            if let Some(end) = find(&buf, b"\r\n\r\n") {
                let headers = String::from_utf8_lossy(&buf[..end]).to_lowercase();
                let len = headers
                    .lines()
                    .find_map(|l| l.strip_prefix("content-length:"))
                    .and_then(|v| v.trim().parse::<usize>().ok())
                    .unwrap_or(0);
                if buf.len() >= end + 4 + len {
                    break;
                }
            }
        }
        stream.write_all(response.as_bytes()).unwrap();
        String::from_utf8_lossy(&buf).into_owned()
    });
    (base, handle)
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

fn settings_with(base: &str) -> Settings {
    Settings {
        gptzero: true,
        gptzero_base_url: base.to_string(),
        ..Settings::default()
    }
}

#[test]
fn documented_response_shape_parses_from_live_fixture() {
    let parsed: DetectResponse = serde_json::from_str(AI_FIXTURE).expect("fixture parses");
    let doc = &parsed.documents[0];
    assert_eq!(doc.predicted_class, "ai");
    assert_eq!(doc.confidence_category, "high");
    assert_eq!(doc.class_probabilities.ai, 1.0);
    assert_eq!(doc.document_classification.as_deref(), Some("AI_ONLY"));
}

#[test]
fn request_carries_key_header_and_document_body() {
    let (base, handle) = serve_once("200 OK", AI_FIXTURE);
    let client = GptZeroClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let parsed = client.detect_text("Some sample text.").expect("ok");
    assert_eq!(parsed.documents[0].predicted_class, "ai");

    let request = handle.join().unwrap().to_lowercase();
    assert!(request.starts_with("post /v2/predict/text "), "{request}");
    assert!(request.contains(&format!("x-api-key: {}", TEST_KEY.to_lowercase())));
    assert!(request.contains("\"document\":\"some sample text.\""));
}

#[test]
fn compare_reports_verdict_and_marks_text_as_sent() {
    let (base, handle) = serve_once("200 OK", AI_FIXTURE);
    let report = compare(&settings_with(&base), "Some sample text.", Some(TEST_KEY));
    handle.join().unwrap();
    assert_eq!(report.status, ExternalStatus::Ok);
    assert!(report.sent);
    assert!(report.informational);
    assert_eq!(report.vendor, "gptzero");
    let verdict = report.verdict.expect("verdict present");
    assert_eq!(verdict.predicted_class, "ai");
}

#[test]
fn unauthorized_key_is_clear_and_never_echoes_the_key() {
    let (base, handle) = serve_once("401 Unauthorized", r#"{"error":"bad key"}"#);
    let report = compare(&settings_with(&base), "Some sample text.", Some(TEST_KEY));
    handle.join().unwrap();
    assert_eq!(report.status, ExternalStatus::Failed);
    let reason = report.reason.clone().expect("reason");
    assert!(reason.contains("GPTZERO_API_KEY"), "{reason}");
    assert!(!reason.contains(TEST_KEY));
    assert!(!format!("{report:?}").contains(TEST_KEY));
}

#[test]
fn forbidden_key_maps_to_unauthorized() {
    let (base, handle) = serve_once("403 Forbidden", "{}");
    let client = GptZeroClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let err = client.detect_text("x").unwrap_err();
    handle.join().unwrap();
    assert_eq!(err, ClientError::Unauthorized);
}

#[test]
fn rate_limit_is_distinct_from_other_http_errors() {
    let (base, handle) = serve_once("429 Too Many Requests", "{}");
    let client = GptZeroClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let err = client.detect_text("x").unwrap_err();
    handle.join().unwrap();
    assert_eq!(err, ClientError::RateLimited);
}

#[test]
fn other_http_status_reports_code_without_body() {
    let (base, handle) = serve_once("500 Internal Server Error", "secret-body-text");
    let client = GptZeroClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let err = client.detect_text("x").unwrap_err();
    handle.join().unwrap();
    assert_eq!(err, ClientError::Http(500));
    assert!(!err.to_string().contains("secret-body-text"));
}

#[test]
fn unparseable_success_body_is_malformed_not_a_panic() {
    let (base, handle) = serve_once("200 OK", r#"{"unexpected":true}"#);
    let client = GptZeroClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let err = client.detect_text("x").unwrap_err();
    handle.join().unwrap();
    assert!(matches!(err, ClientError::Malformed(_)), "{err:?}");
}

#[test]
fn oversize_input_is_refused_before_any_request() {
    // Points at a closed port: if a request were attempted it would fail as Transport instead.
    let client = GptZeroClient::new(
        TEST_KEY.into(),
        "http://127.0.0.1:9",
        Duration::from_secs(1),
    )
    .unwrap();
    let text = "a".repeat(nobotrs::external::gptzero::client::GPTZERO_MAX_CHARS + 1);
    let err = client.detect_text(&text).unwrap_err();
    assert!(matches!(err, ClientError::Oversize { .. }), "{err:?}");

    let report = compare(&settings_with("http://127.0.0.1:9"), &text, Some(TEST_KEY));
    assert_eq!(report.status, ExternalStatus::Failed);
    assert!(!report.sent);
}

#[test]
fn stalled_server_times_out_within_budget() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let _hold = thread::spawn(move || {
        let (_stream, _) = listener.accept().unwrap();
        thread::sleep(Duration::from_secs(3));
    });
    let client = GptZeroClient::new(TEST_KEY.into(), &base, Duration::from_millis(200)).unwrap();
    let started = std::time::Instant::now();
    let err = client.detect_text("x").unwrap_err();
    assert!(
        started.elapsed() < Duration::from_secs(2),
        "took {:?}",
        started.elapsed()
    );
    assert!(matches!(err, ClientError::Transport(_)), "{err:?}");
}

#[test]
fn missing_key_and_empty_text_skip_without_sending() {
    let report = compare(&settings_with("http://127.0.0.1:9"), "Some text.", None);
    assert_eq!(report.status, ExternalStatus::Skipped);
    assert!(!report.sent);

    let report = compare(
        &settings_with("http://127.0.0.1:9"),
        "   \n",
        Some(TEST_KEY),
    );
    assert_eq!(report.status, ExternalStatus::Skipped);
    assert!(!report.sent);
}

#[test]
fn cli_comparison_leaves_verdict_and_exit_code_unchanged() {
    use std::process::Command;
    let bin = env!("CARGO_BIN_EXE_nobotrs");
    let sample =
        std::path::PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join("gptzero_cli_sample.txt");
    std::fs::write(
        &sample,
        "My grandmother kept a notebook by the kitchen phone. Every recipe in it is written in pencil. \
         Some of them were crossed out and rewritten, and the margins are full of her own arguments.\n",
    )
    .unwrap();

    let baseline = Command::new(bin)
        .args(["--format", "json", "detect"])
        .arg(&sample)
        .output()
        .expect("run baseline");

    let (base, handle) = serve_once("200 OK", AI_FIXTURE);
    let with = Command::new(bin)
        .args(["--format", "json", "--gptzero", "detect"])
        .arg(&sample)
        .env("GPTZERO_API_KEY", TEST_KEY)
        .env("NOBOTRS_GPTZERO_BASE_URL", &base)
        .output()
        .expect("run with gptzero");
    handle.join().unwrap();

    assert_eq!(
        baseline.status.code(),
        with.status.code(),
        "exit code must not change"
    );
    let stderr = String::from_utf8_lossy(&with.stderr);
    assert!(stderr.contains("sending"), "{stderr}");
    assert!(!stderr.contains(TEST_KEY), "key leaked to stderr");
    assert!(
        !String::from_utf8_lossy(&with.stdout).contains(TEST_KEY),
        "key leaked to stdout"
    );

    let parse = |out: &std::process::Output| -> serde_json::Value {
        let value: serde_json::Value = serde_json::from_slice(&out.stdout).expect("json stdout");
        match value {
            serde_json::Value::Array(items) => items.into_iter().next().expect("one report"),
            other => other,
        }
    };
    let base_report = parse(&baseline);
    let with_report = parse(&with);
    assert_eq!(
        base_report["verdict"], with_report["verdict"],
        "verdict must not change"
    );
    assert_eq!(
        base_report["families"], with_report["families"],
        "families must not change"
    );
    assert!(
        base_report.get("external").is_none(),
        "external absent when not requested"
    );
    assert_eq!(with_report["external"]["status"], "ok");
    assert_eq!(with_report["external"]["informational"], true);
    assert_eq!(with_report["external"]["verdict"]["predicted_class"], "ai");
}
