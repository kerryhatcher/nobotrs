use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::PathBuf};

pub const BACKENDS: [&str; 7] = [
    "vocabulary",
    "punctuation",
    "burstiness",
    "lexical-diversity",
    "readability",
    "compression",
    "structure",
];
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize, clap::ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum ModelCoverage {
    #[default]
    Opening,
    Full,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Settings {
    pub minimum_severity: crate::score::Severity,
    pub quorum: usize,
    pub max_bytes: usize,
    pub max_candidates: usize,
    pub display_limit: usize,
    pub timeout_ms: u64,
    pub language: Option<String>,
    pub enabled_backends: Vec<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub experiment: Vec<String>,
    /// Optional local evidence backends requested with --models. Empty by default.
    pub models: Vec<String>,
    pub model_coverage: ModelCoverage,
    /// Directory containing the pinned model artifacts described by models/*.json.
    pub models_dir: Option<PathBuf>,
    /// Opt-in: send the analyzed text to GPTZero as informational comparison evidence.
    /// Requires the `api-clients` feature and a `GPTZERO_API_KEY` in the environment.
    /// The key is never a setting and is never read from or written to config files.
    pub gptzero: bool,
    /// Base URL for the GPTZero API. Overridable for proxies and local test servers.
    pub gptzero_base_url: String,
    /// Opt-in: ask an OpenRouter model to judge AI vs human using the writing guide as reference.
    /// Requires the `api-clients` feature and `OPENROUTER_API_KEY`. Informational only.
    pub openrouter_judge: bool,
    /// Pinned OpenRouter model slug used by the judge.
    pub openrouter_model: String,
    /// Base URL for the OpenRouter API. Overridable for proxies and local test servers.
    pub openrouter_base_url: String,
    /// When true (default), only zero-data-retention endpoints that do not train on inputs.
    pub openrouter_strict_privacy: bool,
    pub ignore_rules: Vec<String>,
    pub path_ignores: BTreeMap<String, Vec<String>>,
}
impl Default for Settings {
    fn default() -> Self {
        Self {
            minimum_severity: crate::score::Severity::Medium,
            quorum: 2,
            max_bytes: 1_048_576,
            max_candidates: 10_000,
            display_limit: 200,
            timeout_ms: 5000,
            language: None,
            experiment: Vec::new(),
            enabled_backends: BACKENDS.iter().map(|s| s.to_string()).collect(),
            models: vec![],
            model_coverage: ModelCoverage::Opening,
            models_dir: None,
            gptzero: false,
            gptzero_base_url: "https://api.gptzero.me".into(),
            openrouter_judge: false,
            openrouter_model: crate::external::openrouter::DEFAULT_MODEL.into(),
            openrouter_base_url: crate::external::openrouter::DEFAULT_BASE_URL.into(),
            openrouter_strict_privacy: true,
            ignore_rules: vec![],
            path_ignores: BTreeMap::new(),
        }
    }
}
#[derive(Debug, Serialize)]
pub struct ResolvedConfig {
    pub path: Option<PathBuf>,
    pub settings: Settings,
    pub origins: BTreeMap<String, String>,
}
#[derive(Default)]
pub struct Overrides {
    pub minimum_severity: Option<crate::score::Severity>,
    pub quorum: Option<usize>,
    pub max_bytes: Option<usize>,
    pub max_candidates: Option<usize>,
    pub display_limit: Option<usize>,
    pub timeout_ms: Option<u64>,
    pub language: Option<String>,
    pub models: Option<Vec<String>>,
    pub model_coverage: Option<ModelCoverage>,
    pub models_dir: Option<PathBuf>,
    pub gptzero: Option<bool>,
    pub openrouter_judge: Option<bool>,
    pub openrouter_strict_privacy: Option<bool>,
    pub ignore_rules: Option<Vec<String>>,
}
impl ResolvedConfig {
    pub fn load(path: Option<PathBuf>, cli: Overrides) -> Result<Self, String> {
        let explicit = path.is_some();
        let path = path
            .or_else(|| std::env::var_os("NOBOTRS_CONFIG").map(PathBuf::from))
            .or_else(|| {
                directories::ProjectDirs::from("com", "nobotrs", "nobotrs")
                    .map(|d| d.config_dir().join("config.json"))
            });
        let mut settings = Settings::default();
        let mut origins = BTreeMap::new();
        for key in [
            "minimum_severity",
            "quorum",
            "max_bytes",
            "max_candidates",
            "display_limit",
            "timeout_ms",
            "language",
            "enabled_backends",
            "models",
            "models_dir",
            "model_coverage",
            "gptzero",
            "gptzero_base_url",
            "openrouter_judge",
            "openrouter_model",
            "openrouter_base_url",
            "openrouter_strict_privacy",
            "ignore_rules",
            "path_ignores",
        ] {
            origins.insert(key.into(), "default".into());
        }
        if let Some(p) = &path {
            match std::fs::read_to_string(p) {
                Ok(raw) => {
                    let value: serde_json::Value =
                        serde_json::from_str(&raw).map_err(|e| format!("{}: {e}", p.display()))?;
                    settings = serde_json::from_value(value.clone())
                        .map_err(|e| format!("{}: {e}", p.display()))?;
                    if let Some(keys) = value.as_object() {
                        for key in keys.keys() {
                            origins.insert(key.clone(), format!("file:{}", p.display()));
                        }
                    }
                }
                Err(e)
                    if e.kind() == std::io::ErrorKind::NotFound
                        && !explicit
                        && std::env::var_os("NOBOTRS_CONFIG").is_none() => {}
                Err(e) => return Err(format!("{}: {e}", p.display())),
            }
        }
        macro_rules! setting {
            ($field:ident,$env:literal,$ty:ty) => {
                if let Some(raw) = std::env::var_os($env) {
                    let raw = raw
                        .into_string()
                        .map_err(|_| format!("{} must be UTF-8", $env))?;
                    settings.$field = raw
                        .parse::<$ty>()
                        .map_err(|_| format!("invalid {}: {raw}", $env))?;
                    origins.insert(
                        stringify!($field).into(),
                        concat!("environment:", $env).into(),
                    );
                }
                if let Some(value) = cli.$field {
                    settings.$field = value;
                    origins.insert(stringify!($field).into(), "cli".into());
                }
            };
        }
        if let Some(raw) = std::env::var_os("NOBOTRS_MINIMUM_SEVERITY") {
            let raw = raw
                .into_string()
                .map_err(|_| "NOBOTRS_MINIMUM_SEVERITY must be UTF-8")?;
            settings.minimum_severity = serde_json::from_value(serde_json::Value::String(raw))
                .map_err(|e| e.to_string())?;
            origins.insert(
                "minimum_severity".into(),
                "environment:NOBOTRS_MINIMUM_SEVERITY".into(),
            );
        }
        if let Some(value) = cli.minimum_severity {
            settings.minimum_severity = value;
            origins.insert("minimum_severity".into(), "cli".into());
        }
        if let Some(raw) = env_text("NOBOTRS_MODEL_COVERAGE")? {
            settings.model_coverage = serde_json::from_value(serde_json::Value::String(raw))
                .map_err(|e| e.to_string())?;
            origins.insert(
                "model_coverage".into(),
                "environment:NOBOTRS_MODEL_COVERAGE".into(),
            );
        }
        if let Some(value) = cli.model_coverage {
            settings.model_coverage = value;
            origins.insert("model_coverage".into(), "cli".into());
        }
        setting!(quorum, "NOBOTRS_QUORUM", usize);
        setting!(max_bytes, "NOBOTRS_MAX_BYTES", usize);
        setting!(max_candidates, "NOBOTRS_MAX_CANDIDATES", usize);
        setting!(display_limit, "NOBOTRS_DISPLAY_LIMIT", usize);
        setting!(timeout_ms, "NOBOTRS_TIMEOUT_MS", u64);
        if let Some(raw) = env_text("NOBOTRS_LANGUAGE")? {
            settings.language = Some(raw);
            origins.insert("language".into(), "environment:NOBOTRS_LANGUAGE".into());
        }
        if let Some(raw) = cli.language {
            settings.language = Some(raw);
            origins.insert("language".into(), "cli".into());
        }
        if let Some(raw) = std::env::var_os("NOBOTRS_MODELS_DIR") {
            let raw = raw
                .into_string()
                .map_err(|_| "NOBOTRS_MODELS_DIR must be UTF-8")?;
            settings.models_dir = Some(PathBuf::from(raw));
            origins.insert("models_dir".into(), "environment:NOBOTRS_MODELS_DIR".into());
        }
        if let Some(value) = cli.models_dir {
            settings.models_dir = Some(value);
            origins.insert("models_dir".into(), "cli".into());
        }
        setting!(gptzero, "NOBOTRS_GPTZERO", bool);
        if let Some(raw) = env_text("NOBOTRS_GPTZERO_BASE_URL")? {
            settings.gptzero_base_url = raw;
            origins.insert(
                "gptzero_base_url".into(),
                "environment:NOBOTRS_GPTZERO_BASE_URL".into(),
            );
        }
        setting!(openrouter_judge, "NOBOTRS_OPENROUTER_JUDGE", bool);
        setting!(
            openrouter_strict_privacy,
            "NOBOTRS_OPENROUTER_STRICT_PRIVACY",
            bool
        );
        if let Some(raw) = env_text("NOBOTRS_OPENROUTER_MODEL")? {
            settings.openrouter_model = raw;
            origins.insert(
                "openrouter_model".into(),
                "environment:NOBOTRS_OPENROUTER_MODEL".into(),
            );
        }
        if let Some(raw) = env_text("NOBOTRS_OPENROUTER_BASE_URL")? {
            settings.openrouter_base_url = raw;
            origins.insert(
                "openrouter_base_url".into(),
                "environment:NOBOTRS_OPENROUTER_BASE_URL".into(),
            );
        }
        if let Some(raw) = env_text("NOBOTRS_EXPERIMENT")? {
            settings.experiment = raw
                .split(',')
                .map(str::trim)
                .filter(|s| !s.is_empty())
                .map(str::to_owned)
                .collect();
            origins.insert("experiment".into(), "environment:NOBOTRS_EXPERIMENT".into());
        }
        if let Some(raw) = env_text("NOBOTRS_MODELS")? {
            settings.models = raw
                .split(',')
                .filter(|name| !name.trim().is_empty())
                .map(|name| name.trim().to_string())
                .collect();
            origins.insert("models".into(), "environment:NOBOTRS_MODELS".into());
        }
        if let Some(models) = cli.models {
            settings.models = models
                .into_iter()
                .filter(|name| !name.trim().is_empty())
                .map(|name| name.trim().to_string())
                .collect();
            origins.insert("models".into(), "cli".into());
        }
        if let Some(raw) = env_text("NOBOTRS_IGNORE_RULES")? {
            settings.ignore_rules = raw.split(',').map(str::to_string).collect();
            origins.insert(
                "ignore_rules".into(),
                "environment:NOBOTRS_IGNORE_RULES".into(),
            );
        }
        if let Some(ids) = cli.ignore_rules {
            settings.ignore_rules = ids;
            origins.insert("ignore_rules".into(), "cli".into());
        }
        settings.validate()?;
        Ok(Self {
            path,
            settings,
            origins,
        })
    }
}
impl Settings {
    pub fn experiment_enabled(&self, id: &str) -> bool {
        self.experiment.iter().any(|s| s == id)
    }
    pub fn validate(&self) -> Result<(), String> {
        let mut seen = std::collections::BTreeSet::new();
        for id in &self.experiment {
            if !crate::experiments::IDS.contains(&id.as_str()) || !seen.insert(id) {
                return Err(format!("unknown or repeated experiment: {id}"));
            }
        }
        if !(1..=3).contains(&self.quorum) {
            return Err("quorum must be 1..=3".into());
        }
        if !(1..=16_777_216).contains(&self.max_bytes) {
            return Err("max_bytes must be 1..=16777216".into());
        }
        if !(1..=100_000).contains(&self.max_candidates) {
            return Err("max_candidates must be 1..=100000".into());
        }
        if self.display_limit > 100_000 {
            return Err("display_limit must be at most 100000".into());
        }
        if self.timeout_ms > 3_600_000 {
            return Err("timeout_ms must be at most 3600000".into());
        }
        if self.language.as_ref().is_some_and(|l| {
            l.is_empty() || !l.chars().all(|c| c.is_ascii_alphabetic() || c == '-')
        }) {
            return Err("language must be a language code".into());
        }
        let mut names = std::collections::HashSet::new();
        for name in &self.enabled_backends {
            if !BACKENDS.contains(&name.as_str()) || !names.insert(name) {
                return Err(format!("unknown or duplicate backend: {name}"));
            }
        }
        let mut models = std::collections::HashSet::new();
        for name in &self.models {
            if !crate::models::is_model_backend(name) || !models.insert(name) {
                return Err(format!("unknown or duplicate model: {name}"));
            }
        }
        if let Some(models_dir) = &self.models_dir {
            if models_dir.as_os_str().is_empty() {
                return Err("models_dir must not be empty".into());
            }
        }
        if !(self.gptzero_base_url.starts_with("https://")
            || self.gptzero_base_url.starts_with("http://"))
        {
            return Err("gptzero_base_url must start with http:// or https://".into());
        }
        if !(self.openrouter_base_url.starts_with("https://")
            || self.openrouter_base_url.starts_with("http://"))
        {
            return Err("openrouter_base_url must start with http:// or https://".into());
        }
        if self.openrouter_model.trim().is_empty() {
            return Err("openrouter_model must not be empty".into());
        }
        Ok(())
    }
}

fn env_text(name: &str) -> Result<Option<String>, String> {
    std::env::var_os(name)
        .map(|value| {
            value
                .into_string()
                .map_err(|_| format!("{name} must be UTF-8"))
        })
        .transpose()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn model_settings_deserialize_without_changing_core_defaults() {
        let settings: Settings =
            serde_json::from_str(r#"{"models":["desklib"],"models_dir":"/tmp/models"}"#).unwrap();
        assert_eq!(settings.models, ["desklib"]);
        assert_eq!(
            settings.models_dir.as_deref(),
            Some(std::path::Path::new("/tmp/models"))
        );
        assert_eq!(
            settings.enabled_backends,
            Settings::default().enabled_backends
        );
        assert!(Settings::default().models.is_empty());
    }

    #[test]
    fn gptzero_is_off_by_default_and_has_no_key_field() {
        let defaults = Settings::default();
        assert!(!defaults.gptzero);
        assert_eq!(defaults.gptzero_base_url, "https://api.gptzero.me");
        // A key smuggled into the config file must be rejected, not stored.
        let rejected = serde_json::from_str::<Settings>(r#"{"gptzero_api_key":"secret"}"#).is_err();
        assert!(rejected, "config files must not accept an API key field");
    }

    #[test]
    fn gptzero_base_url_must_be_http_or_https() {
        let mut settings = Settings {
            gptzero_base_url: "ftp://example.test".into(),
            ..Default::default()
        };
        assert!(settings.validate().is_err());
        settings.gptzero_base_url = "http://127.0.0.1:9".into();
        assert!(settings.validate().is_ok());
    }

    #[test]
    fn invalid_or_duplicate_model_requests_fail_validation() {
        let mut settings = Settings {
            models: vec!["not-a-model".into()],
            ..Default::default()
        };
        assert!(settings.validate().is_err());
        settings.models = vec!["desklib".into(), "desklib".into()];
        assert!(settings.validate().is_err());
        settings.models = vec!["desklib".into()];
        settings.models_dir = Some(std::path::PathBuf::new());
        assert!(settings.validate().is_err());
    }
}
