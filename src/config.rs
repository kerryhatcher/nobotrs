use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::PathBuf};

pub const BACKENDS: [&str; 6] = [
    "vocabulary",
    "punctuation",
    "burstiness",
    "lexical-diversity",
    "readability",
    "compression",
];
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
            enabled_backends: BACKENDS.iter().map(|s| s.to_string()).collect(),
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
    pub fn validate(&self) -> Result<(), String> {
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
