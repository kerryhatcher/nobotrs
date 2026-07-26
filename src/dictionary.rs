use crate::backend::SignalFamily;
use regex::RegexBuilder;
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EntryKind {
    Word,
    Phrase,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MatchType {
    Exact,
    Regex,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DictionaryEntry {
    pub id: String,
    pub kind: EntryKind,
    pub match_type: MatchType,
    pub pattern: String,
    #[serde(default)]
    pub variants: Vec<String>,
    #[serde(default = "default_false")]
    pub case_sensitive: bool,
    #[serde(default = "default_true")]
    pub whole_word: bool,
    pub family: SignalFamily,
    pub category: String,
    #[serde(default)]
    pub suggested_replacements: Vec<String>,
    #[serde(default)]
    pub model_era: Vec<String>,
    pub source: Option<String>,
    pub notes: Option<String>,
}

fn default_false() -> bool { false }
fn default_true() -> bool { true }

#[derive(Debug, Clone, Deserialize)]
pub struct Dictionary {
    pub schema_version: String,
    pub dictionary_version: String,
    pub entries: Vec<DictionaryEntry>,
}

const EMBEDDED_JSON: &str = include_str!("../dictionary/entries.json");

impl Dictionary {
    pub fn embedded() -> Dictionary {
        Self::from_json_str(EMBEDDED_JSON).expect("embedded dictionary/entries.json must be valid at compile time")
    }

    pub fn from_json_str(json: &str) -> Result<Dictionary, serde_json::Error> {
        serde_json::from_str(json)
    }

    /// Compiles every `regex`-kind entry's pattern under `size_limit` bytes,
    /// per spec §8/§11.3: a deterministic size bound, not a wall-clock timing
    /// check. Returns the offending entry `id` on the first failure so a bad
    /// contributed pattern fails CI with an actionable message.
    pub fn compiled_regexes(&self, size_limit: usize) -> Result<Vec<(String, regex::Regex)>, String> {
        self.entries
            .iter()
            .filter(|e| matches!(e.match_type, MatchType::Regex))
            .map(|e| {
                RegexBuilder::new(&e.pattern)
                    .case_insensitive(!e.case_sensitive)
                    .size_limit(size_limit)
                    .build()
                    .map(|re| (e.id.clone(), re))
                    .map_err(|err| format!("entry '{}' failed to compile: {err}", e.id))
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_dictionary_parses_without_error() {
        let dict = Dictionary::embedded();
        assert!(!dict.entries.is_empty());
    }

    #[test]
    fn every_entry_family_is_vocabulary() {
        let dict = Dictionary::embedded();
        for entry in &dict.entries {
            assert_eq!(entry.family, crate::backend::SignalFamily::Vocabulary, "entry {} has non-Vocabulary family", entry.id);
        }
    }

    #[test]
    fn case_sensitive_defaults_to_false_when_absent() {
        // parse a minimal single-entry document lacking the field entirely
        let json = r#"{"schema_version":"1.0.0","dictionary_version":"test","entries":[
            {"id":"x","kind":"word","match_type":"exact","pattern":"x","family":"Vocabulary","category":"vocabulary","suggested_replacements":[],"model_era":[],"source":null,"notes":null}
        ]}"#;
        let dict: Dictionary = Dictionary::from_json_str(json).unwrap();
        assert_eq!(dict.entries[0].case_sensitive, false);
        assert_eq!(dict.entries[0].whole_word, true);
    }

    #[test]
    fn all_regex_entries_compile_under_size_limit() {
        let dict = Dictionary::embedded();
        let compiled = dict.compiled_regexes(1 << 16); // 64 KiB, the CI-asserted bound (spec §8, §11.3)
        assert!(compiled.is_ok(), "a dictionary regex failed to compile: {:?}", compiled.err());
    }
}
