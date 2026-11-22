//! Blocking HTTP client for GPTZero `POST /v2/predict/text`.
//!
//! Wire types deliberately parse only the fields this tool uses and ignore everything else:
//! the live API returns many more fields than the public reference documents, and the
//! reference documents may lag behind the service.

use super::ClassProbabilities;
use serde::Deserialize;
use std::fmt;
use std::time::Duration;

/// Documented character limit for API plans; longer text is rejected with HTTP 400.
pub const GPTZERO_MAX_CHARS: usize = 150_000;

#[derive(Debug, Clone, PartialEq)]
pub enum ClientError {
    /// Refused locally before any request was sent.
    Oversize { chars: usize, limit: usize },
    /// HTTP 401 (missing or expired key) or 403 (unrecognized key).
    Unauthorized,
    /// HTTP 429, or a quota/overage decline reported as a rate limit.
    RateLimited,
    /// Any other non-success HTTP status. The response body is never included.
    Http(u16),
    /// Connection, DNS, TLS or timeout failure. Carries no URL.
    Transport(String),
    /// Success status but the body did not match the expected shape.
    Malformed(String),
}

impl fmt::Display for ClientError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ClientError::Oversize { chars, limit } => write!(
                f,
                "input has {chars} characters; GPTZero API plans accept at most {limit}"
            ),
            ClientError::Unauthorized => {
                write!(f, "GPTZero rejected the API key (check GPTZERO_API_KEY)")
            }
            ClientError::RateLimited => {
                write!(f, "GPTZero rate limit or plan quota reached")
            }
            ClientError::Http(code) => write!(f, "GPTZero returned HTTP {code}"),
            ClientError::Transport(msg) => write!(f, "GPTZero request failed: {msg}"),
            ClientError::Malformed(msg) => {
                write!(f, "GPTZero response could not be parsed: {msg}")
            }
        }
    }
}

/// One analyzed document from the `documents` array. Only documented or observed fields.
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct DetectedDocument {
    pub predicted_class: String,
    pub confidence_category: String,
    pub class_probabilities: ClassProbabilities,
    #[serde(default)]
    pub document_classification: Option<String>,
    #[serde(default)]
    pub result_message: Option<String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct DetectResponse {
    pub documents: Vec<DetectedDocument>,
    #[serde(default)]
    pub version: Option<String>,
}

pub struct GptZeroClient {
    http: reqwest::blocking::Client,
    endpoint: String,
    api_key: String,
}

impl GptZeroClient {
    pub fn new(api_key: String, base_url: &str, timeout: Duration) -> Result<Self, ClientError> {
        let http = reqwest::blocking::Client::builder()
            .timeout(timeout)
            .build()
            .map_err(|e| ClientError::Transport(e.without_url().to_string()))?;
        Ok(Self {
            http,
            endpoint: format!("{}/v2/predict/text", base_url.trim_end_matches('/')),
            api_key,
        })
    }

    pub fn detect_text(&self, text: &str) -> Result<DetectResponse, ClientError> {
        let chars = text.chars().count();
        if chars > GPTZERO_MAX_CHARS {
            return Err(ClientError::Oversize {
                chars,
                limit: GPTZERO_MAX_CHARS,
            });
        }
        let response = self
            .http
            .post(&self.endpoint)
            .header("x-api-key", &self.api_key)
            .header("Accept", "application/json")
            .json(&serde_json::json!({ "document": text }))
            .send()
            .map_err(|e| ClientError::Transport(e.without_url().to_string()))?;
        let status = response.status();
        match status.as_u16() {
            401 | 403 => return Err(ClientError::Unauthorized),
            429 => return Err(ClientError::RateLimited),
            code if !status.is_success() => return Err(ClientError::Http(code)),
            _ => {}
        }
        response
            .json::<DetectResponse>()
            .map_err(|e| ClientError::Malformed(e.without_url().to_string()))
    }
}
