use crate::{
    aggregate::{aggregate_backends, BackendOutcome, FamilyDecision, Verdict, Warning},
    backend::{DetectorBackend, ScoreOutcome, SignalFamily},
    backends::{
        burstiness::Burstiness, compression::Compression, lexical_diversity::LexicalDiversity,
        punctuation::Punctuation, readability::Readability, vocabulary::Vocabulary,
    },
    config::Settings,
    deadline::Deadline,
    dictionary::Dictionary,
    document::{Document, Language},
    error::Error,
};
use serde::Serialize;
use std::{collections::HashSet, io::Read, ops::Range, time::Duration};
#[derive(Debug, Serialize)]
pub struct BackendReport {
    pub backend: String,
    pub family: SignalFamily,
    pub outcome: ScoreOutcome,
}
#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: &'static str,
    pub engine_version: &'static str,
    pub dictionary_version: String,
    pub metric_contract: &'static str,
    pub path: String,
    pub settings: Settings,
    pub language: Language,
    pub prose_words: usize,
    pub sentence_count: usize,
    pub block_contexts: Vec<Vec<Range<usize>>>,
    pub sentence_contexts: Vec<Vec<Range<usize>>>,
    pub complete: bool,
    /// Coverage of heuristic analysis. Local models report their excerpt coverage separately.
    pub analyzed_coverage: f64,
    pub incomplete_reasons: Vec<String>,
    pub verdict: Verdict,
    pub families: Vec<FamilyDecision>,
    pub warnings: Vec<Warning>,
    pub backends: Vec<BackendReport>,
    pub effective_finding_count: usize,
    pub actionable_finding_count: usize,
    pub emitted_findings: usize,
    pub omitted_findings: usize,
    pub emitted_candidates: usize,
    pub omitted_candidates: usize,
    pub display_limit: usize,
    pub omitted_document_findings: usize,
}
impl Report {
    pub fn mark_input_truncated(&mut self) {
        self.complete = false;
        self.analyzed_coverage = 0.0; // full size unknown; do not claim a fabricated fraction
        self.incomplete_reasons.push(format!(
            "input byte budget {} exhausted; retained prefix only, total size unknown",
            self.settings.max_bytes
        ));
    }
    pub fn exit_code(&self, lint: bool) -> i32 {
        if !self.complete {
            2
        } else if lint && self.actionable_finding_count > 0
            || !lint && self.verdict == Verdict::Flagged
        {
            1
        } else if self.prose_words == 0 || !lint && self.verdict == Verdict::Inconclusive {
            3
        } else {
            0
        }
    }
}
pub struct Engine {
    vocabulary: Vocabulary,
    backends: Vec<Box<dyn DetectorBackend>>,
    dictionary_version: String,
    known: HashSet<String>,
}
impl Engine {
    pub fn new() -> Result<Self, String> {
        let dictionary = Dictionary::embedded();
        let mut known: HashSet<_> = dictionary.entries.iter().map(|e| e.id.clone()).collect();
        known.extend(["punctuation.em-dash-density", "statistics.burstiness"].map(str::to_string));
        Ok(Self {
            dictionary_version: dictionary.dictionary_version.clone(),
            vocabulary: Vocabulary::new(dictionary)?,
            backends: vec![
                Box::new(Punctuation),
                Box::new(Burstiness),
                Box::new(LexicalDiversity),
                Box::new(Readability),
                Box::new(Compression),
            ],
            known,
        })
    }
    pub fn validate_settings(&self, settings: &Settings) -> Result<(), String> {
        settings.validate()?;
        for id in settings
            .ignore_rules
            .iter()
            .chain(settings.path_ignores.values().flatten())
        {
            if !self.known.contains(id) {
                return Err(format!("unknown suppressed rule ID: {id}"));
            }
        }
        Ok(())
    }
    pub fn analyze(
        &self,
        raw: String,
        markdown: bool,
        path: &str,
        settings: &Settings,
    ) -> Result<Report, String> {
        let models = crate::models::ModelRegistry::resolve(settings)?;
        self.analyze_with_models(raw, markdown, path, settings, &models)
    }

    /// Analyze with optional local model evidence. Model backends are informational:
    /// they never enter the heuristic family decision or quorum.
    pub fn analyze_with_models(
        &self,
        raw: String,
        markdown: bool,
        path: &str,
        settings: &Settings,
        models: &crate::models::ModelRegistry,
    ) -> Result<Report, String> {
        self.validate_settings(settings)?;
        let deadline = Deadline::new(Duration::from_millis(settings.timeout_ms));
        if raw.len() > settings.max_bytes {
            return Err(format!("input exceeds {} bytes", settings.max_bytes));
        }
        // An expired preparation has no safely completed prose to score. Keep the
        // ordinary report/exit contract and let all enabled backends fail closed.
        let mut doc = match Document::from_stdin_text_with_deadline(raw, markdown, deadline) {
            Ok(doc) => doc,
            Err(Error::Timeout) => Document::from_stdin_text(String::new(), markdown),
            Err(error) => return Err(error.to_string()),
        };
        doc.assert_language(settings.language.as_deref());
        let directives = if deadline.expired() {
            Vec::new()
        } else {
            match crate::suppression::directives_with_deadline(
                &doc,
                settings,
                path,
                &self.known,
                deadline,
            ) {
                Ok(directives) => directives,
                Err(_) if deadline.expired() => Vec::new(),
                Err(error) => return Err(error),
            }
        };
        let registry: Vec<&dyn DetectorBackend> =
            std::iter::once(&self.vocabulary as &dyn DetectorBackend)
                .chain(self.backends.iter().map(|b| b.as_ref()))
                .chain(models.backends().iter().map(|b| b.as_ref()))
                .filter(|b| {
                    if b.family() == SignalFamily::Model {
                        settings.models.iter().any(|n| n == b.name())
                    } else {
                        settings.enabled_backends.iter().any(|n| n == b.name())
                    }
                })
                .collect();
        let mut names = HashSet::new();
        let mut outcomes = vec![];
        let mut coverage = 1.0_f64;
        for backend in &registry {
            if !names.insert(backend.name()) {
                return Err("duplicate backend identity".into());
            }
            let mut outcome = if deadline.expired() {
                ScoreOutcome::Failed(Error::Timeout)
            } else if doc.words.is_empty() && backend.family() != SignalFamily::Model {
                // Model backends receive empty/short prose so they can emit a typed
                // applicability/length abstention instead of a generic heuristic one.
                ScoreOutcome::Abstained {
                    reason: "no analyzable prose".into(),
                    model: None,
                }
            } else if backend.name() == "vocabulary" {
                self.vocabulary
                    .score_limited(&doc, deadline, settings.max_candidates)
            } else if backend.name() == "punctuation" {
                Punctuation.score_limited(&doc, deadline, settings.max_candidates)
            } else {
                backend.score(&doc, deadline)
            };
            if let ScoreOutcome::Scored(mut score) = outcome {
                let suppression_error =
                    crate::suppression::apply(&mut score, &directives, deadline).err();
                outcome = if deadline.expired() || suppression_error.is_some() {
                    score.voting_eligible = false;
                    ScoreOutcome::Incomplete {
                        score,
                        reason: suppression_error.unwrap_or(Error::Timeout),
                        coverage: 0.0,
                    }
                } else {
                    ScoreOutcome::Scored(score)
                };
            }
            if backend.family() != SignalFamily::Model {
                match &outcome {
                    ScoreOutcome::Incomplete { coverage: c, .. } => coverage = coverage.min(*c),
                    ScoreOutcome::Failed(_) => coverage = 0.0,
                    _ => {}
                }
            }
            outcomes.push(BackendOutcome {
                backend: backend.name().into(),
                family: backend.family(),
                outcome,
            });
        }
        let result = aggregate_backends(outcomes, settings.quorum)?;
        let mut backends: Vec<_> = registry
            .iter()
            .zip(result.outcomes)
            .map(|(b, (family, outcome))| BackendReport {
                backend: b.name().into(),
                family,
                outcome,
            })
            .collect();
        let effective_finding_count = backends
            .iter()
            .map(|b| match &b.outcome {
                ScoreOutcome::Scored(s) | ScoreOutcome::Incomplete { score: s, .. } => {
                    s.evidence.len()
                        + s.document_findings
                            .iter()
                            .filter(|f| f.suppression.is_none())
                            .count()
                }
                _ => 0,
            })
            .sum();
        let actionable_finding_count = backends
            .iter()
            .map(|b| match &b.outcome {
                ScoreOutcome::Scored(s) | ScoreOutcome::Incomplete { score: s, .. } => {
                    s.evidence
                        .iter()
                        .filter(|e| e.severity >= settings.minimum_severity)
                        .count()
                        + s.document_findings
                            .iter()
                            .filter(|f| {
                                f.suppression.is_none() && f.severity >= settings.minimum_severity
                            })
                            .count()
                }
                _ => 0,
            })
            .sum();
        let mut omitted_document_findings = 0;
        let mut emitted = 0;
        let mut emitted_candidates = 0;
        let mut omitted_candidates = 0;
        for b in &mut backends {
            if let ScoreOutcome::Scored(s) | ScoreOutcome::Incomplete { score: s, .. } =
                &mut b.outcome
            {
                let n = s
                    .evidence
                    .len()
                    .min(settings.display_limit.saturating_sub(emitted));
                s.evidence.truncate(n);
                emitted += n;
                let n = s
                    .document_findings
                    .len()
                    .min(settings.display_limit.saturating_sub(emitted));
                omitted_document_findings += s.document_findings.len() - n;
                s.document_findings.truncate(n);
                emitted += s
                    .document_findings
                    .iter()
                    .filter(|f| f.suppression.is_none())
                    .count();
                let n = s
                    .candidates
                    .len()
                    .min(settings.display_limit.saturating_sub(emitted_candidates));
                omitted_candidates += s.candidates.len() - n;
                s.candidates.truncate(n);
                emitted_candidates += n;
            }
        }
        let mut incomplete_reasons: Vec<_> = result
            .warnings
            .iter()
            .map(|w| w.error.to_string())
            .collect();
        let block_contexts = doc
            .prose_spans
            .iter()
            .map(|r| doc.source_ranges(r.clone()))
            .collect();
        let sentence_contexts = doc
            .sentences
            .iter()
            .map(|r| doc.source_ranges(r.clone()))
            .collect();
        if deadline.expired() && incomplete_reasons.is_empty() {
            incomplete_reasons.push(Error::Timeout.to_string());
            coverage = 0.0;
        }
        Ok(Report {
            schema_version: "1.0.0",
            engine_version: env!("CARGO_PKG_VERSION"),
            dictionary_version: self.dictionary_version.clone(),
            metric_contract: "prepared-prose-v1/uncalibrated",
            path: path.into(),
            settings: settings.clone(),
            language: doc.language,
            prose_words: doc.words.len(),
            sentence_count: doc.sentences.len(),
            block_contexts,
            sentence_contexts,
            complete: incomplete_reasons.is_empty(),
            analyzed_coverage: coverage,
            incomplete_reasons,
            verdict: result.verdict,
            families: result.families,
            warnings: result.warnings,
            backends,
            effective_finding_count,
            actionable_finding_count,
            emitted_findings: emitted,
            omitted_findings: effective_finding_count - emitted,
            emitted_candidates,
            omitted_candidates,
            display_limit: settings.display_limit,
            omitted_document_findings,
        })
    }
}
/// Prefix retained when the byte budget stops reading. Total stream size is deliberately unknown.
pub struct ReadInput {
    pub text: String,
    pub truncated: bool,
}
pub fn read_bounded(reader: impl Read, limit: usize) -> Result<ReadInput, String> {
    let mut bytes = vec![];
    reader
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    let truncated = bytes.len() > limit;
    bytes.truncate(limit);
    let text = match String::from_utf8(bytes) {
        Ok(text) => text,
        Err(error) if truncated && error.utf8_error().error_len().is_none() => {
            let end = error.utf8_error().valid_up_to();
            String::from_utf8(error.into_bytes()[..end].to_vec())
                .map_err(|e| format!("invalid UTF-8: {e}"))?
        }
        Err(error) => return Err(format!("invalid UTF-8: {error}")),
    };
    Ok(ReadInput { text, truncated })
}
