mod manifest;

use crate::{
    availability::Availability,
    backend::{DetectorBackend, ScoreOutcome, SignalFamily},
    config::Settings,
    deadline::Deadline,
    document::Document,
    error::Error,
    score::Score,
};
use manifest::{ArtifactState, ModelManifest};
use serde::Serialize;
use std::{
    collections::HashSet,
    path::{Path, PathBuf},
    sync::OnceLock,
};

pub use manifest::ModelManifest as Manifest;

pub const MODEL_BACKENDS: [&str; 3] = ["desklib", "conpara", "detectorscope"];
pub const MODEL_FAMILY: SignalFamily = SignalFamily::Model;

pub fn is_model_backend(name: &str) -> bool {
    MODEL_BACKENDS.contains(&name)
}

const DESKLIB: &str = include_str!("../../models/desklib.json");
const CONPARA: &str = include_str!("../../models/conpara.json");
const DETECTORSCOPE: &str = include_str!("../../models/detectorscope.json");

pub fn manifests() -> &'static [ModelManifest] {
    static MANIFESTS: OnceLock<Vec<ModelManifest>> = OnceLock::new();
    MANIFESTS.get_or_init(|| {
        [DESKLIB, CONPARA, DETECTORSCOPE]
            .iter()
            .map(|raw| serde_json::from_str(raw).expect("embedded model manifest is valid"))
            .collect()
    })
}

pub fn manifest(id: &str) -> Option<&'static ModelManifest> {
    manifests().iter().find(|m| m.id == id)
}

pub fn compiled(id: &str) -> bool {
    (matches!(id, "desklib" | "conpara") && cfg!(feature = "models-encoders"))
        || (id == "detectorscope" && cfg!(feature = "models-detectorscope"))
}

/// Availability is deliberately report-only here: answering `config` never loads a tokenizer or model.
#[derive(Debug, Clone, Serialize)]
pub struct ModelStatus {
    pub backend: String,
    pub display_name: String,
    pub known: bool,
    pub compiled: bool,
    pub artifacts: String,
    pub enabled: bool,
    pub availability: String,
    pub reason: Option<String>,
    pub model_revision: Option<String>,
    pub runtime: Option<String>,
    pub max_tokens: Option<usize>,
}

pub fn statuses(settings: &Settings) -> Vec<ModelStatus> {
    settings
        .models
        .iter()
        .map(|id| status_for(id, settings))
        .chain(
            MODEL_BACKENDS
                .iter()
                .filter(|id| !settings.models.iter().any(|requested| requested == *id))
                .map(|id| status_for(id, settings)),
        )
        .collect()
}

fn status_for(id: &str, settings: &Settings) -> ModelStatus {
    let Some(m) = manifest(id) else {
        return ModelStatus {
            backend: id.into(),
            display_name: id.into(),
            known: false,
            compiled: false,
            artifacts: ArtifactState::Missing.as_str().into(),
            enabled: settings.models.iter().any(|requested| requested == id),
            availability: "unknown".into(),
            reason: Some("unknown model backend".into()),
            model_revision: None,
            runtime: None,
            max_tokens: None,
        };
    };
    let compiled = compiled(id);
    let artifacts = m.artifact_state(settings.models_dir.as_deref());
    let enabled = settings.models.iter().any(|requested| requested == id);
    let (availability, reason) = if !compiled {
        (
            "not_compiled".to_string(),
            Some(format!(
                "rebuild with Cargo feature {}",
                m.runtime.cargo_feature
            )),
        )
    } else if artifacts != ArtifactState::Present {
        (
            "artifacts_unavailable".to_string(),
            Some(if artifacts == ArtifactState::NotConfigured {
                "no models directory configured".to_string()
            } else {
                format!("model directory artifact state: {}", artifacts.as_str())
            }),
        )
    } else if let Some(reason) = runtime_reason(id, settings) {
        ("runtime_unavailable".to_string(), Some(reason))
    } else {
        ("ready".to_string(), None)
    };
    ModelStatus {
        backend: m.id.clone(),
        display_name: m.display_name.clone(),
        known: true,
        compiled,
        artifacts: artifacts.as_str().into(),
        enabled,
        availability,
        reason,
        model_revision: Some(m.upstream.revision.clone()),
        runtime: Some(m.runtime.kind.clone()),
        max_tokens: Some(m.max_tokens),
    }
}

fn runtime_reason(id: &str, settings: &Settings) -> Option<String> {
    if id != "detectorscope" {
        return None;
    }
    let root = settings.models_dir.as_deref()?;
    let source = std::env::var_os("NOBOTRS_DETECTORSCOPE_SOURCE")
        .map(PathBuf::from)
        .unwrap_or_else(|| root.join("detectorscope/source"));
    if !source.is_dir() {
        return Some(format!(
            "DetectorScope source checkout not found at {}",
            source.display()
        ));
    }
    if let Some(python) = std::env::var_os("NOBOTRS_MODEL_PYTHON") {
        let path = Path::new(&python);
        let available = if path.file_name() == Some(python.as_os_str()) {
            std::env::var_os("PATH").is_some_and(|search| {
                std::env::split_paths(&search).any(|dir| dir.join(path).is_file())
            })
        } else {
            path.is_file()
        };
        if !available {
            return Some(format!(
                "NOBOTRS_MODEL_PYTHON does not exist: {}",
                Path::new(&python).display()
            ));
        }
    }
    None
}

/// A validated request. Construction checks support and artifact presence, not inference.
pub struct ModelRegistry {
    backends: Vec<Box<dyn DetectorBackend>>,
}

impl ModelRegistry {
    pub fn empty() -> Self {
        Self { backends: vec![] }
    }

    pub fn resolve(settings: &Settings) -> Result<Self, String> {
        if settings.models.is_empty() {
            return Ok(Self::empty());
        }
        let root = settings.models_dir.as_deref();
        let mut names = HashSet::new();
        let mut backends: Vec<Box<dyn DetectorBackend>> = vec![];
        for id in &settings.models {
            let m = manifest(id).ok_or_else(|| format!("unknown model backend: {id}"))?;
            if !names.insert(id.as_str()) {
                return Err(format!("duplicate model backend: {id}"));
            }
            let Some(root) = root else {
                backends.push(Box::new(FailedBackend::new(
                    id,
                    Error::ModelLoadFailed(format!(
                        "model {id} requires a models directory (--models-dir or NOBOTRS_MODELS_DIR)"
                    )),
                )));
                continue;
            };
            if !compiled(id) {
                backends.push(Box::new(FailedBackend::new(
                    id,
                    Error::ModelLoadFailed(format!(
                        "model {id} is not compiled into this build; rebuild with Cargo feature {}",
                        m.runtime.cargo_feature
                    )),
                )));
                continue;
            }
            match m.artifact_state(Some(root)) {
                ArtifactState::Present => {}
                state => {
                    backends.push(Box::new(FailedBackend::new(
                        id,
                        Error::ModelLoadFailed(format!(
                            "model {id} artifacts are {} under {}; run scripts/prepare_local_models.py or stage the pinned artifacts",
                            state.as_str(),
                            root.display()
                        )),
                    )));
                    continue;
                }
            }
            match make_backend(m, root) {
                Ok(backend) => backends.push(backend),
                Err(message) => backends.push(Box::new(FailedBackend::new(
                    id,
                    Error::ModelLoadFailed(message),
                ))),
            }
        }
        Ok(Self { backends })
    }

    pub fn backends(&self) -> &[Box<dyn DetectorBackend>] {
        &self.backends
    }

    pub fn is_empty(&self) -> bool {
        self.backends.is_empty()
    }
}

struct FailedBackend {
    name: String,
    error: Error,
}

impl FailedBackend {
    fn new(name: &str, error: Error) -> Self {
        Self {
            name: name.into(),
            error,
        }
    }
}

impl DetectorBackend for FailedBackend {
    fn name(&self) -> &str {
        &self.name
    }
    fn family(&self) -> SignalFamily {
        MODEL_FAMILY
    }
    fn availability(&self) -> Availability {
        Availability::Unavailable(self.error.to_string())
    }
    fn score(&self, _doc: &Document, _deadline: Deadline) -> ScoreOutcome {
        ScoreOutcome::Failed(self.error.clone())
    }
}

fn make_backend(
    m: &'static ModelManifest,
    root: &Path,
) -> Result<Box<dyn DetectorBackend>, String> {
    match m.id.as_str() {
        "desklib" | "conpara" => encoder_backend(m, root),
        "detectorscope" => detectorscope_backend(m, root),
        id => Err(format!("no factory for model backend: {id}")),
    }
}

#[cfg(feature = "models-encoders")]
fn encoder_backend(
    m: &'static ModelManifest,
    root: &Path,
) -> Result<Box<dyn DetectorBackend>, String> {
    Ok(Box::new(encoders::EncoderBackend::new(m, root)?))
}

#[cfg(not(feature = "models-encoders"))]
fn encoder_backend(
    _m: &'static ModelManifest,
    _root: &Path,
) -> Result<Box<dyn DetectorBackend>, String> {
    Err("encoder support is not compiled".into())
}

#[cfg(feature = "models-detectorscope")]
fn detectorscope_backend(
    m: &'static ModelManifest,
    root: &Path,
) -> Result<Box<dyn DetectorBackend>, String> {
    Ok(Box::new(detectorscope::DetectorScopeBackend::new(m, root)?))
}

#[cfg(not(feature = "models-detectorscope"))]
fn detectorscope_backend(
    _m: &'static ModelManifest,
    _root: &Path,
) -> Result<Box<dyn DetectorBackend>, String> {
    Err("DetectorScope worker support is not compiled".into())
}

/// Shared model evidence attached to a completed or attempted model score.
#[derive(Debug, Clone, Serialize)]
pub struct ModelEvidence {
    pub backend: String,
    pub model_revision: String,
    pub tokenizer_revision: String,
    pub code_revision: Option<String>,
    pub runtime: String,
    pub device: String,
    pub precision: String,
    pub preprocessing_revision: String,
    pub raw_output: f64,
    pub raw_units: String,
    pub threshold: Option<f64>,
    pub threshold_source: Option<String>,
    pub prepared_bytes: usize,
    pub prepared_words: usize,
    pub excerpt_bytes: usize,
    pub excerpt_tokens: usize,
    pub token_limit: usize,
    pub truncated: bool,
    /// Coverage planned from tokenizer boundaries before inference starts.
    pub planned_coverage: Option<f64>,
    /// Coverage actually executed; separate from the plan so failures do not claim it.
    pub execution_coverage: Option<f64>,
    /// Retained character coverage alias retained for report readers.
    pub excerpt_coverage: Option<f64>,
    pub elapsed_ms: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detectorscope: Option<DetectorScopeEvidence>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct PlannedExcerpt {
    pub prepared_bytes: usize,
    pub prepared_words: usize,
    pub excerpt_bytes: usize,
    pub excerpt_tokens: usize,
    pub token_limit: usize,
    pub truncated: bool,
    pub coverage: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DetectorScopeEvidence {
    pub bias: f64,
    pub reconstruction_residual: f64,
    pub active_features: usize,
    pub feature_filter: f64,
    pub formatting_profile: String,
    pub top_features: Vec<FeatureContribution>,
    pub omitted_features: usize,
    pub remainder: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct FeatureContribution {
    pub id: usize,
    pub description: String,
    pub contribution: f64,
    pub highlights: Vec<FeatureHighlight>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FeatureHighlight {
    pub token_index: usize,
    pub text: String,
    pub activation: f64,
    pub prose_ranges: Vec<std::ops::Range<usize>>,
    pub source_ranges: Vec<std::ops::Range<usize>>,
}

#[cfg(any(feature = "models-encoders", feature = "models-detectorscope"))]
pub fn read_verified(path: &Path, expected: &str) -> Result<Vec<u8>, Error> {
    use sha2::{Digest, Sha256};
    let mut data = std::fs::read(path)
        .map_err(|e| Error::ModelLoadFailed(format!("{}: {e}", path.display())))?;
    if format!("{:x}", Sha256::digest(&data)) != expected {
        return Err(Error::ChecksumMismatch);
    }
    // Keep the buffer alive only for the caller that consumes it.
    data.shrink_to_fit();
    Ok(data)
}

#[cfg(feature = "models-encoders")]
mod encoders;
#[cfg(feature = "models-encoders")]
mod normalize;

#[cfg(feature = "models-encoders")]
fn normalize_input(text: &str) -> String {
    normalize::conpara_input(text)
}

#[cfg(feature = "models-detectorscope")]
mod detectorscope;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelAbstentionCode {
    LanguageUnknown,
    LanguageUnsupported,
    TextTooShort,
}

#[derive(Debug, Clone, Serialize)]
pub struct ModelAbstention {
    pub backend: String,
    pub code: ModelAbstentionCode,
    pub detail: String,
    pub prepared_words: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub minimum_words: Option<usize>,
}

pub fn model_failure(message: String, planned: Option<PlannedExcerpt>) -> Error {
    Error::ModelFailure {
        message,
        planned: planned.map(Box::new),
    }
}

/// Typed model abstentions keep applicability and length policy visible.
pub fn abstain(
    backend: &str,
    code: ModelAbstentionCode,
    detail: &str,
    prepared_words: usize,
    minimum_words: Option<usize>,
) -> ScoreOutcome {
    ScoreOutcome::Abstained {
        reason: format!(
            "{}: {detail}",
            match code {
                ModelAbstentionCode::LanguageUnknown => "model_language_unknown",
                ModelAbstentionCode::LanguageUnsupported => "model_language_unsupported",
                ModelAbstentionCode::TextTooShort => "model_text_too_short",
            }
        ),
        model: Some(ModelAbstention {
            backend: backend.into(),
            code,
            detail: detail.into(),
            prepared_words,
            minimum_words,
        }),
    }
}

pub fn model_score(backend: &str) -> Score {
    Score::new(
        backend.into(),
        SignalFamily::Model,
        crate::score::ConfidenceTier::Low,
        crate::score::VoteStrength::None,
        vec![],
    )
}

pub fn unavailable(_backend: &str, _doc: &Document, _deadline: Deadline) -> Availability {
    Availability::Unavailable("model runtime not loaded".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manifests_are_pinned_and_models_are_informational() {
        let ids: Vec<_> = manifests().iter().map(|m| m.id.as_str()).collect();
        assert_eq!(ids, MODEL_BACKENDS);
        for m in manifests() {
            assert_eq!(m.schema_version, "1.0.0");
            assert!(!m.upstream.revision.is_empty());
            assert!(m.tokenizer.as_ref().is_none_or(|t| !t.sha256.is_empty()));
            assert!(!m.artifacts.is_empty());
            assert!(m.licenses.is_object());
        }
        let score = model_score("desklib");
        assert_eq!(score.family, SignalFamily::Model);
        assert!(!score.voting_eligible);
        assert_eq!(score.vote, crate::score::VoteStrength::None);
    }

    #[test]
    fn config_status_does_not_require_a_models_directory() {
        let mut settings = Settings::default();
        assert!(settings.models.is_empty());
        settings.models = vec!["detectorscope".into()];
        let status = status_for("detectorscope", &settings);
        assert!(status.known);
        assert!(status.enabled);
        assert_eq!(status.artifacts, "not_configured");
    }
}
