//! Opt-in GPTZero comparison. Its output is informational: it is attached to a report as a
//! side channel and never enters the heuristic families, quorum, or exit verdict.
//!
//! The report types always compile so the output schema is identical in every build. Only the
//! HTTP client is gated behind the `api-clients` feature.

#[cfg(feature = "api-clients")]
pub mod client;

use crate::config::Settings;
use crate::external::ExternalStatus;
use serde::{Deserialize, Serialize};

pub const VENDOR: &str = "gptzero";
/// Network budget for one request. Deliberately separate from the heuristic `timeout_ms`.
#[cfg(feature = "api-clients")]
const REQUEST_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(30);

#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
pub struct ClassProbabilities {
    pub human: f64,
    pub ai: f64,
    pub mixed: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct GptZeroVerdict {
    pub predicted_class: String,
    pub confidence_category: String,
    pub document_classification: Option<String>,
    pub class_probabilities: ClassProbabilities,
    pub result_message: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExternalReport {
    pub vendor: &'static str,
    /// Always true: this evidence never enters the heuristic verdict.
    pub informational: bool,
    pub status: ExternalStatus,
    pub reason: Option<String>,
    /// Whether the text was transmitted to the vendor.
    pub sent: bool,
    pub input_characters: usize,
    pub verdict: Option<GptZeroVerdict>,
}

impl ExternalReport {
    fn new(status: ExternalStatus, reason: Option<String>, input_characters: usize) -> Self {
        Self {
            vendor: VENDOR,
            informational: true,
            status,
            reason,
            sent: false,
            input_characters,
            verdict: None,
        }
    }
}

/// Built without the `api-clients` feature: always reports, never sends.
#[cfg(not(feature = "api-clients"))]
pub fn compare(_settings: &Settings, text: &str, _api_key: Option<&str>) -> ExternalReport {
    ExternalReport::new(
        ExternalStatus::Failed,
        Some("this build has no GPTZero support; rebuild with --features api-clients".into()),
        text.chars().count(),
    )
}

/// Runs the comparison for `text`. Never fails: every outcome is recorded in the returned
/// report so the heuristic verdict and exit code are unaffected by GPTZero availability.
#[cfg(feature = "api-clients")]
pub fn compare(settings: &Settings, text: &str, api_key: Option<&str>) -> ExternalReport {
    use client::{ClientError, GptZeroClient, GPTZERO_MAX_CHARS};

    let input_characters = text.chars().count();
    let Some(key) = api_key.map(str::trim).filter(|k| !k.is_empty()) else {
        return ExternalReport::new(
            ExternalStatus::Skipped,
            Some("GPTZERO_API_KEY is not set".into()),
            input_characters,
        );
    };
    if text.trim().is_empty() {
        return ExternalReport::new(
            ExternalStatus::Skipped,
            Some("no analyzable text; no request was sent".into()),
            input_characters,
        );
    }
    if input_characters > GPTZERO_MAX_CHARS {
        let error = ClientError::Oversize {
            chars: input_characters,
            limit: GPTZERO_MAX_CHARS,
        };
        return ExternalReport::new(
            ExternalStatus::Failed,
            Some(error.to_string()),
            input_characters,
        );
    }
    let client =
        match GptZeroClient::new(key.to_string(), &settings.gptzero_base_url, REQUEST_TIMEOUT) {
            Ok(client) => client,
            Err(error) => {
                return ExternalReport::new(
                    ExternalStatus::Failed,
                    Some(error.to_string()),
                    input_characters,
                )
            }
        };
    eprintln!("nobotrs: sending {input_characters} characters to GPTZero (enabled with --gptzero)");
    let mut report = ExternalReport::new(ExternalStatus::Failed, None, input_characters);
    report.sent = true;
    match client.detect_text(text) {
        Ok(response) => match response.documents.into_iter().next() {
            Some(doc) => {
                report.status = ExternalStatus::Ok;
                report.verdict = Some(GptZeroVerdict {
                    predicted_class: doc.predicted_class,
                    confidence_category: doc.confidence_category,
                    document_classification: doc.document_classification,
                    class_probabilities: doc.class_probabilities,
                    result_message: doc.result_message,
                });
            }
            None => {
                report.reason = Some("GPTZero response contained no documents".into());
            }
        },
        Err(error) => report.reason = Some(error.to_string()),
    }
    report
}
