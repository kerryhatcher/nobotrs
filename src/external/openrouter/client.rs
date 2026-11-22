//! Blocking HTTP client for OpenRouter `POST /api/v1/chat/completions`.
//!
//! Error values carry status codes and OpenRouter's machine-readable reason codes only. Neither
//! the API key nor the response body is ever included in an error.

use serde::Deserialize;
use std::fmt;
use std::time::Duration;

#[derive(Debug, Clone, PartialEq)]
pub enum ClientError {
    /// Refused locally before any request was sent.
    Oversize { chars: usize, limit: usize },
    /// HTTP 401: missing, invalid, or disabled key.
    Unauthorized,
    /// HTTP 402. `transient` is true only for the in-flight budget, which clears after a wait.
    InsufficientCredits { reason: String, transient: bool },
    /// HTTP 429. `retry_after` is the `Retry-After` value in seconds, when sent.
    RateLimited { retry_after: Option<u64> },
    /// HTTP 502 or 503: model or routing unavailable.
    ProviderUnavailable(u16),
    /// HTTP 400 or 403: the request was rejected. The message is the API's short error text.
    Rejected { status: u16, message: String },
    /// Any other non-success HTTP status.
    Http(u16),
    /// Connection, DNS, TLS or timeout failure. Carries no URL.
    Transport(String),
    /// Success status but the body did not match the expected shape or had no content.
    Malformed(String),
}

impl fmt::Display for ClientError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ClientError::Oversize { chars, limit } => write!(
                f,
                "input has {chars} characters; the judge accepts at most {limit}"
            ),
            ClientError::Unauthorized => {
                write!(
                    f,
                    "OpenRouter rejected the API key (check OPENROUTER_API_KEY)"
                )
            }
            ClientError::InsufficientCredits { reason, transient } => {
                if *transient {
                    write!(
                        f,
                        "OpenRouter in-flight budget exhausted ({reason}); retry later"
                    )
                } else {
                    write!(f, "OpenRouter credit or key limit reached ({reason})")
                }
            }
            ClientError::RateLimited { retry_after } => match retry_after {
                Some(s) => write!(f, "OpenRouter rate limit reached; retry after {s} s"),
                None => write!(f, "OpenRouter rate limit reached"),
            },
            ClientError::ProviderUnavailable(code) => {
                write!(f, "OpenRouter model or routing unavailable (HTTP {code})")
            }
            ClientError::Rejected { status, message } => {
                write!(
                    f,
                    "OpenRouter rejected the request (HTTP {status}): {message}"
                )
            }
            ClientError::Http(code) => write!(f, "OpenRouter returned HTTP {code}"),
            ClientError::Transport(msg) => write!(f, "OpenRouter request failed: {msg}"),
            ClientError::Malformed(msg) => {
                write!(f, "OpenRouter response could not be used: {msg}")
            }
        }
    }
}

/// Content and accounting from a successful completion.
#[derive(Debug, Clone, PartialEq)]
pub struct ChatReply {
    pub content: String,
    pub finish_reason: Option<String>,
    pub model: Option<String>,
    pub provider: Option<String>,
    pub prompt_tokens: Option<u64>,
    pub completion_tokens: Option<u64>,
    pub cost: Option<f64>,
}

/// One chat completion request: a system prompt and a user message.
pub struct ChatRequest<'a> {
    pub model: &'a str,
    pub system: &'a str,
    pub user: &'a str,
    pub max_completion_tokens: u32,
    /// When true, send `provider.data_collection = "deny"` and `provider.zdr = true`, so only
    /// zero-retention endpoints that do not train on inputs are eligible.
    pub strict_privacy: bool,
}

pub struct OpenRouterClient {
    http: reqwest::blocking::Client,
    endpoint: String,
    api_key: String,
}

#[derive(Deserialize)]
struct WireResponse {
    #[serde(default)]
    choices: Vec<WireChoice>,
    #[serde(default)]
    usage: Option<WireUsage>,
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    provider: Option<String>,
    #[serde(default)]
    error: Option<WireError>,
}

#[derive(Deserialize)]
struct WireChoice {
    #[serde(default)]
    finish_reason: Option<String>,
    message: WireMessage,
}

#[derive(Deserialize)]
struct WireMessage {
    #[serde(default)]
    content: Option<String>,
}

#[derive(Deserialize)]
struct WireUsage {
    #[serde(default)]
    prompt_tokens: Option<u64>,
    #[serde(default)]
    completion_tokens: Option<u64>,
    #[serde(default)]
    cost: Option<f64>,
}

#[derive(Deserialize)]
struct WireError {
    #[serde(default)]
    code: Option<u16>,
    #[serde(default)]
    message: Option<String>,
    #[serde(default)]
    metadata: Option<serde_json::Value>,
}

impl OpenRouterClient {
    pub fn new(api_key: String, base_url: &str, timeout: Duration) -> Result<Self, ClientError> {
        let http = reqwest::blocking::Client::builder()
            .timeout(timeout)
            .build()
            .map_err(|e| ClientError::Transport(e.without_url().to_string()))?;
        Ok(Self {
            http,
            endpoint: format!("{}/chat/completions", base_url.trim_end_matches('/')),
            api_key,
        })
    }

    /// Builds the JSON body. Exposed so tests can check the privacy fields without a network call.
    pub fn request_body(req: &ChatRequest<'_>) -> serde_json::Value {
        let mut body = serde_json::json!({
            "model": req.model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "temperature": 0,
            "max_completion_tokens": req.max_completion_tokens,
            "stream": false,
        });
        if req.strict_privacy {
            body["provider"] = serde_json::json!({
                "data_collection": "deny",
                "zdr": true,
            });
        }
        body
    }

    pub fn chat(&self, req: &ChatRequest<'_>) -> Result<ChatReply, ClientError> {
        let response = self
            .http
            .post(&self.endpoint)
            .bearer_auth(&self.api_key)
            .header("Accept", "application/json")
            .json(&Self::request_body(req))
            .send()
            .map_err(|e| ClientError::Transport(e.without_url().to_string()))?;
        let status = response.status();
        let retry_after = response
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.trim().parse::<u64>().ok());
        if !status.is_success() {
            let body: Option<WireResponse> = response.json().ok();
            let error = body.and_then(|b| b.error);
            return Err(map_status(status.as_u16(), error, retry_after));
        }
        let body: WireResponse = response
            .json()
            .map_err(|e| ClientError::Malformed(e.without_url().to_string()))?;
        if let Some(error) = body.error {
            // Some failures arrive as HTTP 200 with an error object in the body.
            let code = error.code.unwrap_or(200);
            return Err(map_status(code, Some(error), retry_after));
        }
        let choice = body
            .choices
            .into_iter()
            .next()
            .ok_or_else(|| ClientError::Malformed("no choices in response".into()))?;
        let content = choice.message.content.unwrap_or_default();
        if content.trim().is_empty() {
            let reason = choice.finish_reason.as_deref().unwrap_or("unknown");
            return Err(ClientError::Malformed(format!(
                "empty completion (finish_reason {reason})"
            )));
        }
        let usage = body.usage;
        Ok(ChatReply {
            content,
            finish_reason: choice.finish_reason,
            model: body.model,
            provider: body.provider,
            prompt_tokens: usage.as_ref().and_then(|u| u.prompt_tokens),
            completion_tokens: usage.as_ref().and_then(|u| u.completion_tokens),
            cost: usage.and_then(|u| u.cost),
        })
    }
}

fn map_status(status: u16, error: Option<WireError>, retry_after: Option<u64>) -> ClientError {
    let metadata = error.as_ref().and_then(|e| e.metadata.as_ref());
    let reason = metadata
        .and_then(|m| m.get("reason"))
        .and_then(|v| v.as_str())
        .unwrap_or("unspecified")
        .to_string();
    let message = error
        .as_ref()
        .and_then(|e| e.message.clone())
        .unwrap_or_default();
    match status {
        401 => ClientError::Unauthorized,
        402 => ClientError::InsufficientCredits {
            transient: reason == "in_flight_budget_exhausted",
            reason,
        },
        429 => ClientError::RateLimited { retry_after },
        502 | 503 => ClientError::ProviderUnavailable(status),
        400 | 403 => ClientError::Rejected {
            status,
            message: truncate(&message, 200),
        },
        other => ClientError::Http(other),
    }
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let head: String = s.chars().take(max).collect();
        format!("{head}...")
    }
}
