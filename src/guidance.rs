//! Canonical editorial guidance. Provenance is distinct from utility validation.
use serde::{Deserialize, Serialize};
use std::{collections::HashSet, sync::OnceLock};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Category {
    Content,
    Structure,
    Rhythm,
    Punctuation,
    Formatting,
    Vocabulary,
}
impl Category {
    pub fn leverage(self) -> u8 {
        match self {
            Self::Content => 1,
            Self::Structure => 2,
            Self::Rhythm => 3,
            Self::Punctuation | Self::Formatting => 4,
            Self::Vocabulary => 5,
        }
    }
}
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Example {
    pub before: String,
    pub after: String,
}
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GuidanceEntry {
    pub id: String,
    pub rules: Vec<String>,
    pub category: Category,
    pub leverage: u8,
    pub title: String,
    pub why: String,
    pub fix: String,
    pub keep_when: String,
    pub examples: Vec<Example>,
    pub sources: Vec<String>,
    pub time_bound: bool,
}
#[derive(Debug, Deserialize, Serialize)]
pub struct Guidance {
    pub schema_version: String,
    pub guidance_version: String,
    #[serde(default)]
    pub brief: String,
    pub entries: Vec<GuidanceEntry>,
}
impl Guidance {
    pub fn embedded() -> &'static Self {
        static DATA: OnceLock<Guidance> = OnceLock::new();
        DATA.get_or_init(|| {
            let mut data: Self = serde_json::from_str(include_str!("../guidance/guidance.json"))
                .expect("embedded guidance JSON");
            data.brief = include_str!("../guidance/brief.md").into();
            data.validate().expect("valid embedded guidance");
            data
        })
    }
    pub fn for_rule(&self, rule_id: &str) -> Option<&GuidanceEntry> {
        self.entries
            .iter()
            .find(|e| e.rules.iter().any(|r| r == rule_id))
    }
    pub fn validate(&self) -> Result<(), String> {
        if self.schema_version != "1.0.0" {
            return Err("unsupported guidance schema".into());
        }
        let mut ids = HashSet::new();
        let mut rules = HashSet::new();
        for e in &self.entries {
            if e.id.is_empty()
                || !ids.insert(&e.id)
                || e.rules.is_empty()
                || e.leverage != e.category.leverage()
                || [&e.title, &e.why, &e.fix, &e.keep_when]
                    .iter()
                    .any(|s| s.trim().is_empty())
                || e.examples.is_empty()
                || e.sources.is_empty()
            {
                return Err(format!("invalid guidance entry: {}", e.id));
            }
            for rule in &e.rules {
                if rule.is_empty() || !rules.insert(rule) {
                    return Err(format!("duplicate/empty rule: {rule}"));
                }
            }
        }
        Ok(())
    }
}
/// A mapping is accepted only when its guidance target exists and a human review is recorded.
pub fn detectorscope_guidance(feature_id: usize) -> Option<&'static GuidanceEntry> {
    static MAPPING: OnceLock<serde_json::Value> = OnceLock::new();
    let v = MAPPING.get_or_init(|| {
        serde_json::from_str(include_str!("../guidance/detectorscope-features.json"))
            .expect("feature mapping JSON")
    });
    let entry = v["features"]
        .as_array()?
        .iter()
        .find(|e| e["id"].as_u64() == Some(feature_id as u64))?;
    if entry["reviewed_by"].as_str()?.trim().is_empty()
        || entry["reviewed_on"].as_str()?.trim().is_empty()
    {
        return None;
    }
    let id = entry["guidance_id"].as_str()?;
    Guidance::embedded().entries.iter().find(|g| g.id == id)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn embedded_guidance_validates_and_covers_exact_registry() {
        let g = Guidance::embedded();
        g.validate().unwrap();
        let mut expected: HashSet<String> = crate::dictionary::Dictionary::embedded()
            .entries
            .iter()
            .map(|e| e.id.clone())
            .collect();
        expected
            .extend(["punctuation.em-dash-density", "statistics.burstiness"].map(str::to_string));
        expected.extend(
            crate::backends::structure::RULE_IDS
                .iter()
                .map(|s| s.to_string()),
        );
        expected.extend(crate::copyediting::RULE_IDS.iter().map(|s| s.to_string()));
        let actual: HashSet<String> = g.entries.iter().flat_map(|e| e.rules.clone()).collect();
        assert_eq!(expected, actual);
    }
    #[test]
    fn leverage_scale_is_fixed() {
        use Category::*;
        assert_eq!(
            [
                Content,
                Structure,
                Rhythm,
                Punctuation,
                Formatting,
                Vocabulary
            ]
            .map(Category::leverage),
            [1, 2, 3, 4, 4, 5]
        );
    }
    #[test]
    fn mapping_guidance_ids_exist_and_require_human_review() {
        let v: serde_json::Value =
            serde_json::from_str(include_str!("../guidance/detectorscope-features.json")).unwrap();
        assert_eq!(
            v["detectorscope_revision"],
            crate::models::manifest("detectorscope")
                .unwrap()
                .upstream
                .revision
        );
        for e in v["features"].as_array().unwrap() {
            if let Some(id) = e["guidance_id"].as_str() {
                assert!(Guidance::embedded().entries.iter().any(|g| g.id == id));
                assert!(!e["reviewed_by"].as_str().unwrap().trim().is_empty());
                assert!(!e["reviewed_on"].as_str().unwrap().trim().is_empty());
            }
        }
        assert!(detectorscope_guidance(usize::MAX).is_none());
    }
}
