use serde::Serialize;
use std::{collections::BTreeMap, ops::Range};

#[derive(
    Debug,
    Clone,
    Copy,
    PartialEq,
    Eq,
    PartialOrd,
    Ord,
    Serialize,
    serde::Deserialize,
    clap::ValueEnum,
)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Low,
    Medium,
    High,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ConfidenceTier {
    Low,
    Medium,
    High,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum VoteStrength {
    None,
    Suspicious,
    Strong,
}

#[derive(Debug, Clone, Serialize)]
pub struct Evidence {
    pub rule_id: String,
    /// Bounding range for navigation only; replacements must use source_ranges.
    pub raw_offset: Range<usize>,
    pub source_ranges: Vec<Range<usize>>,
    pub prose_offset: Range<usize>,
    pub line: u32,
    pub column: u32,
    pub end_line: u32,
    pub end_column: u32,
    pub sentence_context: Option<usize>,
    pub block_context: Option<usize>,
    pub matched_text: String,
    pub severity: Severity,
    pub suggestion: Option<String>,
    pub disposition: String,
    pub suppression: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Metric {
    pub value: f64,
    pub unit: String,
    pub method: String,
}
#[derive(Debug, Clone, Serialize)]
pub struct DocumentFinding {
    pub rule_id: String,
    pub severity: Severity,
    pub message: String,
    pub suggestion: Option<String>,
    pub suppression: Option<String>,
}
#[derive(Debug, Clone, Serialize)]
pub struct Score {
    pub backend: String,
    pub family: crate::backend::SignalFamily,
    pub confidence: ConfidenceTier,
    pub vote: VoteStrength,
    pub voting_eligible: bool,
    pub metrics: BTreeMap<String, Metric>,
    pub evidence: Vec<Evidence>,
    pub candidates: Vec<Evidence>,
    pub document_findings: Vec<DocumentFinding>,
}
impl Score {
    pub fn new(
        backend: String,
        family: crate::backend::SignalFamily,
        confidence: ConfidenceTier,
        vote: VoteStrength,
        evidence: Vec<Evidence>,
    ) -> Self {
        let voting_eligible = matches!(
            family,
            crate::backend::SignalFamily::Vocabulary
                | crate::backend::SignalFamily::Punctuation
                | crate::backend::SignalFamily::Burstiness
        );
        Self {
            backend,
            family,
            confidence,
            vote,
            voting_eligible,
            metrics: BTreeMap::new(),
            document_findings: vec![],
            candidates: evidence.clone(),
            evidence,
        }
    }
    pub fn metric(mut self, name: &str, value: f64, unit: &str, method: &str) -> Self {
        assert!(value.is_finite(), "nonfinite metric");
        self.metrics.insert(
            name.into(),
            Metric {
                value,
                unit: unit.into(),
                method: method.into(),
            },
        );
        self
    }
}
