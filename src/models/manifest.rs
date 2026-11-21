use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::Path};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct UpstreamPin {
    pub repo: String,
    pub revision: String,
    #[serde(default)]
    pub checkpoint_sha256: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CodePin {
    pub repo: String,
    pub revision: String,
    #[serde(default)]
    pub source_license: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RuntimePin {
    pub kind: String,
    pub cargo_feature: String,
    pub precision: String,
    pub device: String,
    #[serde(default)]
    pub worker: Option<String>,
    #[serde(default)]
    pub protocol: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TokenizerPin {
    pub repo: String,
    pub revision: String,
    pub file: String,
    pub sha256: String,
    pub bytes: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ArtifactPin {
    pub path: String,
    pub sha256: String,
    pub bytes: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct HeadPin {
    pub name: String,
    pub path: String,
    pub sha256: String,
    pub threshold: f64,
    pub feature_filter: f64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ModelManifest {
    pub schema_version: String,
    pub id: String,
    pub display_name: String,
    #[serde(default)]
    pub architecture: Option<String>,
    pub upstream: UpstreamPin,
    #[serde(default)]
    pub code: Option<CodePin>,
    pub runtime: RuntimePin,
    pub preprocessing_revision: String,
    pub max_tokens: usize,
    #[serde(default)]
    pub minimum_words: Option<usize>,
    #[serde(default)]
    pub thresholds: BTreeMap<String, f64>,
    #[serde(default)]
    pub tokenizer: Option<TokenizerPin>,
    #[serde(default)]
    pub head: Option<HeadPin>,
    pub artifacts: Vec<ArtifactPin>,
    pub licenses: serde_json::Value,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactState {
    Present,
    Missing,
    MismatchedSize,
    NotConfigured,
}

impl ArtifactState {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Present => "present",
            Self::Missing => "missing",
            Self::MismatchedSize => "mismatched_size",
            Self::NotConfigured => "not_configured",
        }
    }
}

impl ModelManifest {
    pub fn artifact_path(&self, root: &Path, artifact: &ArtifactPin) -> std::path::PathBuf {
        root.join(&artifact.path)
    }

    /// Existence and declared size are cheap config checks; hashes are verified before load.
    pub fn artifact_state(&self, root: Option<&Path>) -> ArtifactState {
        let Some(root) = root else {
            return ArtifactState::NotConfigured;
        };
        if self.artifacts.is_empty() {
            return ArtifactState::Present;
        }
        let mut state = ArtifactState::Present;
        for artifact in &self.artifacts {
            match std::fs::metadata(self.artifact_path(root, artifact)) {
                Ok(metadata) if metadata.len() == artifact.bytes => {}
                Ok(_) => return ArtifactState::MismatchedSize,
                Err(_) => state = ArtifactState::Missing,
            }
        }
        state
    }

    pub fn threshold(&self, key: &str) -> Option<f64> {
        self.thresholds.get(key).copied()
    }
}
