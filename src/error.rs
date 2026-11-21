// src/error.rs

/// Recoverable vs. unrecoverable failure modes a `DetectorBackend` can surface.
/// Split explicitly so callers (the `config` command, `detect`'s `warnings`
/// surface, log output) can distinguish "retry/reconfigure" from "reinstall."
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub enum Error {
    Timeout,
    ResourceLimit(String),
    ModelMissing,
    ModelLoadFailed(String),
    ChecksumMismatch,
    NetworkError(String),
    ConfigError(String),
    InternalError(String),
    /// A model failure after input preparation, retaining planned excerpt metadata
    /// without changing the ScoreOutcome contract or claiming executed coverage.
    ModelFailure {
        message: String,
        planned: Option<Box<crate::models::PlannedExcerpt>>,
    },
}

impl Error {
    pub fn is_recoverable(&self) -> bool {
        !matches!(self, Error::ChecksumMismatch | Error::InternalError(_))
    }
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::Timeout => write!(f, "analysis deadline exceeded"),
            Error::ResourceLimit(msg) => write!(f, "resource limit: {msg}"),
            Error::ModelMissing => write!(
                f,
                "model missing; optional model installation is not available"
            ),
            Error::ModelLoadFailed(msg) => write!(f, "model load failed: {msg}"),
            Error::ChecksumMismatch => write!(f, "checksum mismatch (reinstall required)"),
            Error::NetworkError(msg) => write!(f, "network error: {msg}"),
            Error::ConfigError(msg) => write!(f, "config error: {msg}"),
            Error::InternalError(msg) => write!(f, "internal error: {msg}"),
            Error::ModelFailure { message, planned } => {
                write!(f, "{message}")?;
                if let Some(planned) = planned {
                    write!(
                        f,
                        " (planned excerpt {} tokens/limit {}{}, coverage {:.4}; executed coverage 0)",
                        planned.excerpt_tokens,
                        planned.token_limit,
                        if planned.truncated { ", truncated" } else { "" },
                        planned.coverage.unwrap_or(0.0)
                    )?;
                }
                Ok(())
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn checksum_mismatch_is_not_recoverable() {
        assert!(!Error::ChecksumMismatch.is_recoverable());
    }

    #[test]
    fn internal_error_is_not_recoverable() {
        assert!(!Error::InternalError("bug".into()).is_recoverable());
    }

    #[test]
    fn model_missing_is_recoverable() {
        assert!(Error::ModelMissing.is_recoverable());
    }

    #[test]
    fn network_error_is_recoverable() {
        assert!(Error::NetworkError("timeout".into()).is_recoverable());
    }
}
