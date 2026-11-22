//! OpenRouter judge tests against a local mock server. No test contacts the real API.
#![cfg(feature = "api-clients")]

use nobotrs::config::Settings;
use nobotrs::external::openrouter::client::{ChatRequest, ClientError, OpenRouterClient};
use nobotrs::external::openrouter::{judge, DEFAULT_MODEL};
use nobotrs::external::ExternalStatus;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::process::Command;
use std::thread::{self, JoinHandle};
use std::time::Duration;

const TEST_KEY: &str = "or-test-key-do-not-leak-4242";

fn ok_body(content: &str) -> String {
    serde_json::json!({
        "id": "gen-1",
        "object": "chat.completion",
        "created": 1,
        "model": DEFAULT_MODEL,
        "system_fingerprint": null,
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": content}
        }],
        "usage": {"prompt_tokens": 12000, "completion_tokens": 300, "total_tokens": 12300, "cost": 0.0042}
    })
    .to_string()
}

/// Serves exactly one HTTP request with optional extra response headers. Returns the raw request.
fn serve_once(status: &str, extra_headers: &str, body: &str) -> (String, JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock server");
    let base = format!("http://{}/api/v1", listener.local_addr().unwrap());
    let response = format!(
        "HTTP/1.1 {status}\r\nContent-Type: application/json\r\n{extra_headers}Content-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("accept");
        stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut buf = Vec::new();
        let mut chunk = [0u8; 8192];
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

fn settings_with(base: &str, strict: bool) -> Settings {
    Settings {
        openrouter_judge: true,
        openrouter_base_url: base.to_string(),
        openrouter_strict_privacy: strict,
        ..Settings::default()
    }
}

fn request_body(raw: &str) -> serde_json::Value {
    let body = raw.split("\r\n\r\n").nth(1).expect("request has a body");
    serde_json::from_str(body).expect("request body is JSON")
}

#[test]
fn strict_privacy_request_carries_zdr_and_deny_collection() {
    let (base, handle) = serve_once("200 OK", "", &ok_body("VERDICT: AI\nCONFIDENCE: 90"));
    let report = judge(
        &settings_with(&base, true),
        "A passage to judge.",
        Some(TEST_KEY),
    );
    let raw = handle.join().unwrap();

    assert_eq!(report.status, ExternalStatus::Ok);
    assert!(raw.starts_with("POST /api/v1/chat/completions "), "{raw}");
    assert!(raw.to_lowercase().contains(&format!(
        "authorization: bearer {}",
        TEST_KEY.to_lowercase()
    )));
    let body = request_body(&raw);
    assert_eq!(body["model"], DEFAULT_MODEL);
    assert_eq!(body["provider"]["zdr"], true);
    assert_eq!(body["provider"]["data_collection"], "deny");
    assert_eq!(body["stream"], false);
    assert_eq!(body["max_completion_tokens"], 25_000);
}

#[test]
fn relaxed_privacy_omits_provider_restrictions() {
    let (base, handle) = serve_once("200 OK", "", &ok_body("VERDICT: HUMAN\nCONFIDENCE: 60"));
    let report = judge(
        &settings_with(&base, false),
        "A passage to judge.",
        Some(TEST_KEY),
    );
    let raw = handle.join().unwrap();
    assert_eq!(report.status, ExternalStatus::Ok);
    assert!(request_body(&raw).get("provider").is_none());
}

#[test]
fn verdict_and_accounting_are_reported() {
    let (base, handle) = serve_once(
        "200 OK",
        "",
        &ok_body("**VERDICT:** mixed\n**CONFIDENCE:** 55"),
    );
    let report = judge(
        &settings_with(&base, true),
        "A passage to judge.",
        Some(TEST_KEY),
    );
    handle.join().unwrap();
    let verdict = report.verdict.expect("verdict");
    assert_eq!(verdict.label, "MIXED");
    assert_eq!(verdict.confidence, Some(55));
    assert_eq!(report.prompt_tokens, Some(12000));
    assert_eq!(report.cost, Some(0.0042));
    assert!(report.sent && report.informational);
}

#[test]
fn unparseable_reply_is_failed_and_kept_for_inspection() {
    let (base, handle) = serve_once("200 OK", "", &ok_body("I would rather not label this."));
    let report = judge(
        &settings_with(&base, true),
        "A passage to judge.",
        Some(TEST_KEY),
    );
    handle.join().unwrap();
    assert_eq!(report.status, ExternalStatus::Failed);
    assert!(report.verdict.is_none());
    assert_eq!(
        report.unparsed_reply.as_deref(),
        Some("I would rather not label this.")
    );
}

#[test]
fn unauthorized_maps_to_clear_message_without_key() {
    let (base, handle) = serve_once(
        "401 Unauthorized",
        "",
        r#"{"error":{"code":401,"message":"Invalid credentials"}}"#,
    );
    let report = judge(&settings_with(&base, true), "A passage.", Some(TEST_KEY));
    handle.join().unwrap();
    assert_eq!(report.status, ExternalStatus::Failed);
    let reason = report.reason.clone().expect("reason");
    assert!(reason.contains("OPENROUTER_API_KEY"), "{reason}");
    assert!(!format!("{report:?}").contains(TEST_KEY));
}

#[test]
fn in_flight_budget_402_is_transient() {
    let body = r#"{"error":{"code":402,"message":"busy","metadata":{"reason":"in_flight_budget_exhausted","limit_source":"openrouter_in_flight_budget"}}}"#;
    let (base, handle) = serve_once("402 Payment Required", "Retry-After: 5\r\n", body);
    let client = OpenRouterClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let err = client.chat(&chat_request(true)).unwrap_err();
    handle.join().unwrap();
    assert_eq!(
        err,
        ClientError::InsufficientCredits {
            reason: "in_flight_budget_exhausted".into(),
            transient: true
        }
    );
}

#[test]
fn weight_exceeds_budget_is_not_transient() {
    let body = r#"{"error":{"code":402,"message":"too big","metadata":{"reason":"weight_exceeds_budget"}}}"#;
    let (base, handle) = serve_once("402 Payment Required", "", body);
    let client = OpenRouterClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let err = client.chat(&chat_request(true)).unwrap_err();
    handle.join().unwrap();
    assert!(
        matches!(
            err,
            ClientError::InsufficientCredits {
                transient: false,
                ..
            }
        ),
        "{err:?}"
    );
}

#[test]
fn rate_limit_reports_retry_after() {
    let (base, handle) = serve_once("429 Too Many Requests", "Retry-After: 7\r\n", "{}");
    let client = OpenRouterClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let err = client.chat(&chat_request(true)).unwrap_err();
    handle.join().unwrap();
    assert_eq!(
        err,
        ClientError::RateLimited {
            retry_after: Some(7)
        }
    );
}

#[test]
fn provider_unavailable_and_rejection_are_distinct() {
    let (base, handle) = serve_once("503 Service Unavailable", "", "{}");
    let client = OpenRouterClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    assert_eq!(
        client.chat(&chat_request(true)).unwrap_err(),
        ClientError::ProviderUnavailable(503)
    );
    handle.join().unwrap();

    let body = r#"{"error":{"code":400,"message":"model not found"}}"#;
    let (base, handle) = serve_once("400 Bad Request", "", body);
    let client = OpenRouterClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let err = client.chat(&chat_request(true)).unwrap_err();
    handle.join().unwrap();
    assert!(
        matches!(err, ClientError::Rejected { status: 400, .. }),
        "{err:?}"
    );
}

#[test]
fn error_object_inside_http_200_is_mapped() {
    let body = r#"{"error":{"code":402,"message":"no credits","metadata":{"reason":"openrouter_key_limit"}}}"#;
    let (base, handle) = serve_once("200 OK", "", body);
    let client = OpenRouterClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let err = client.chat(&chat_request(true)).unwrap_err();
    handle.join().unwrap();
    assert!(
        matches!(
            err,
            ClientError::InsufficientCredits {
                transient: false,
                ..
            }
        ),
        "{err:?}"
    );
}

#[test]
fn empty_completion_reports_finish_reason() {
    let body = serde_json::json!({
        "choices": [{"index": 0, "finish_reason": "length", "message": {"role": "assistant", "content": ""}}]
    })
    .to_string();
    let (base, handle) = serve_once("200 OK", "", &body);
    let client = OpenRouterClient::new(TEST_KEY.into(), &base, Duration::from_secs(5)).unwrap();
    let err = client.chat(&chat_request(true)).unwrap_err();
    handle.join().unwrap();
    match err {
        ClientError::Malformed(msg) => assert!(msg.contains("length"), "{msg}"),
        other => panic!("expected Malformed, got {other:?}"),
    }
}

#[test]
fn oversize_passage_is_refused_before_any_request() {
    let text = "a ".repeat(nobotrs::external::openrouter::MAX_JUDGE_CHARS);
    let report = judge(
        &settings_with("http://127.0.0.1:9/api/v1", true),
        &text,
        Some(TEST_KEY),
    );
    assert_eq!(report.status, ExternalStatus::Failed);
    assert!(!report.sent);
}

#[test]
fn missing_key_and_empty_text_skip_without_sending() {
    let report = judge(
        &settings_with("http://127.0.0.1:9/api/v1", true),
        "Some text.",
        None,
    );
    assert_eq!(report.status, ExternalStatus::Skipped);
    assert!(!report.sent);
    let report = judge(
        &settings_with("http://127.0.0.1:9/api/v1", true),
        "  \n",
        Some(TEST_KEY),
    );
    assert_eq!(report.status, ExternalStatus::Skipped);
    assert!(!report.sent);
}

#[test]
fn stalled_server_times_out_within_budget() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let base = format!("http://{}/api/v1", listener.local_addr().unwrap());
    let _hold = thread::spawn(move || {
        let (_stream, _) = listener.accept().unwrap();
        thread::sleep(Duration::from_secs(3));
    });
    let client = OpenRouterClient::new(TEST_KEY.into(), &base, Duration::from_millis(200)).unwrap();
    let started = std::time::Instant::now();
    let err = client.chat(&chat_request(true)).unwrap_err();
    assert!(started.elapsed() < Duration::from_secs(2));
    assert!(matches!(err, ClientError::Transport(_)), "{err:?}");
}

#[test]
fn cli_judgment_leaves_verdict_and_exit_code_unchanged() {
    let bin = env!("CARGO_BIN_EXE_nobotrs");
    let sample =
        std::path::PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join("openrouter_cli_sample.txt");
    std::fs::write(
        &sample,
        "My grandmother kept a notebook by the kitchen phone. Every recipe in it is written in pencil. \
         Some were crossed out and rewritten, and the margins hold her arguments with herself.\n",
    )
    .unwrap();

    let baseline = Command::new(bin)
        .args(["--format", "json", "detect"])
        .arg(&sample)
        .output()
        .expect("baseline");

    let (base, handle) = serve_once("200 OK", "", &ok_body("VERDICT: HUMAN\nCONFIDENCE: 70"));
    let with = Command::new(bin)
        .args(["--format", "json", "--openrouter-judge", "detect"])
        .arg(&sample)
        .env("OPENROUTER_API_KEY", TEST_KEY)
        .env("NOBOTRS_OPENROUTER_BASE_URL", &base)
        .output()
        .expect("with judge");
    let raw = handle.join().unwrap();

    assert_eq!(
        baseline.status.code(),
        with.status.code(),
        "exit code must not change"
    );
    let stderr = String::from_utf8_lossy(&with.stderr);
    assert!(stderr.contains("sending"), "{stderr}");
    assert!(
        !stderr.contains(TEST_KEY) && !String::from_utf8_lossy(&with.stdout).contains(TEST_KEY)
    );
    assert!(raw.contains("zdr"), "strict privacy is the default");

    let parse = |out: &std::process::Output| -> serde_json::Value {
        let value: serde_json::Value = serde_json::from_slice(&out.stdout).expect("json");
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
    assert!(base_report.get("openrouter").is_none());
    assert_eq!(with_report["openrouter"]["status"], "ok");
    assert_eq!(with_report["openrouter"]["verdict"]["label"], "HUMAN");
    assert_eq!(with_report["openrouter"]["informational"], true);
}

fn chat_request(strict: bool) -> ChatRequest<'static> {
    ChatRequest {
        model: DEFAULT_MODEL,
        system: "system",
        user: "user",
        max_completion_tokens: 1024,
        strict_privacy: strict,
    }
}
