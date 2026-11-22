//! Advisory editorial report built from suppressed, unsliced analysis outcomes.
use crate::{
    backend::ScoreOutcome,
    config::BACKENDS,
    document::Document,
    guidance::{Category, Guidance},
    pipeline::Report,
    score::{Evidence, Severity},
    sentences::{sentence_units, UnitKind},
};
use serde::Serialize;
use std::{collections::BTreeMap, ops::Range};

#[derive(Debug, Clone, Serialize)]
pub struct ReviewLocation {
    pub line: u32,
    pub column: u32,
    pub end_line: u32,
    pub end_column: u32,
    pub source_ranges: Vec<Range<usize>>,
}
#[derive(Debug, Clone, Serialize)]
pub struct ReviewFinding {
    pub rule_id: String,
    pub guidance_id: String,
    pub category: Category,
    pub leverage: u8,
    pub severity: Severity,
    pub suppressed: bool,
    pub location: Option<ReviewLocation>,
    pub matched_text: String,
    pub sentence: Option<String>,
    pub context: Option<String>,
    pub suggestion: Option<String>,
    pub message: Option<String>,
    pub why: String,
    pub fix: String,
    pub keep_when: String,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CheckStatus {
    Pass,
    Fail,
    Unknown,
    NotApplicable,
}
#[derive(Debug, Serialize)]
pub struct CheckItem {
    pub id: &'static str,
    pub status: CheckStatus,
    pub detail: String,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AnalysisStatus {
    Completed,
    Skipped,
    Incomplete,
}
#[derive(Debug, Serialize)]
pub struct AnalysisCheck {
    pub backend: String,
    pub status: AnalysisStatus,
    pub reason: Option<String>,
}
#[derive(Debug, Serialize)]
pub struct ReviewReport {
    pub schema_version: &'static str,
    pub review_version: &'static str,
    pub path: String,
    pub guidance_version: String,
    pub complete: bool,
    pub prose_words: usize,
    pub leverage_counts: BTreeMap<u8, usize>,
    pub findings: Vec<ReviewFinding>,
    pub document: Vec<ReviewFinding>,
    pub checklist: Vec<CheckItem>,
    pub checks: Vec<AnalysisCheck>,
    pub total_findings: usize,
    pub suppressed_findings: usize,
    pub omitted_findings: usize,
    pub incomplete_reasons: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hotspots: Option<crate::hotspots::HotspotReport>,
}
impl ReviewReport {
    pub fn mark_input_truncated(&mut self) {
        self.complete = false;
        self.incomplete_reasons
            .push("input byte budget exhausted; retained prefix only, total size unknown".into());
    }
}
fn finding(id: &str, severity: Severity, suppressed: bool) -> Option<ReviewFinding> {
    let g = Guidance::embedded().for_rule(id)?;
    Some(ReviewFinding {
        rule_id: id.into(),
        guidance_id: g.id.clone(),
        category: g.category,
        leverage: g.leverage,
        severity,
        suppressed,
        location: None,
        matched_text: String::new(),
        sentence: None,
        context: None,
        suggestion: None,
        message: None,
        why: g.why.clone(),
        fix: g.fix.clone(),
        keep_when: g.keep_when.clone(),
    })
}
fn score(outcome: &ScoreOutcome) -> Option<&crate::score::Score> {
    match outcome {
        ScoreOutcome::Scored(s) | ScoreOutcome::Incomplete { score: s, .. } => Some(s),
        _ => None,
    }
}
pub fn review(report: &Report, doc: &Document) -> ReviewReport {
    let units = doc
        .editorial_units
        .as_ref()
        .map(std::borrow::Cow::Borrowed)
        .unwrap_or_else(|| std::borrow::Cow::Owned(sentence_units(doc)));
    let mut checks = Vec::new();
    for name in BACKENDS
        .iter()
        .copied()
        .chain(report.settings.models.iter().map(String::as_str))
    {
        let (status, reason) = match report
            .backends
            .iter()
            .find(|b| b.backend == name)
            .map(|b| &b.outcome)
        {
            Some(ScoreOutcome::Scored(_)) => (AnalysisStatus::Completed, None),
            Some(ScoreOutcome::Abstained { reason, .. }) => {
                (AnalysisStatus::Skipped, Some(reason.clone()))
            }
            Some(ScoreOutcome::Incomplete { reason, .. }) | Some(ScoreOutcome::Failed(reason)) => {
                (AnalysisStatus::Incomplete, Some(reason.to_string()))
            }
            None => (
                AnalysisStatus::Skipped,
                Some("disabled by configuration".into()),
            ),
        };
        checks.push(AnalysisCheck {
            backend: name.into(),
            status,
            reason,
        });
    }
    let dictionary: Vec<&Evidence> = report
        .backends
        .iter()
        .filter(|b| b.backend == "vocabulary")
        .filter_map(|b| score(&b.outcome))
        .flat_map(|s| s.candidates.iter())
        .filter(|e| e.disposition == "selected" && e.suppression.is_none())
        .collect();
    let mut all = Vec::new();
    for b in &report.backends {
        let Some(s) = score(&b.outcome) else {
            continue;
        };
        for e in &s.candidates {
            if !matches!(e.disposition.as_str(), "selected" | "suppressed") {
                continue;
            }
            if e.rule_id == "structure.negative-parallelism"
                && dictionary.iter().any(|d| {
                    d.rule_id == "not-just-x-but-y"
                        && d.raw_offset.start < e.raw_offset.end
                        && e.raw_offset.start < d.raw_offset.end
                })
            {
                continue;
            }
            if e.rule_id == "structure.significance-inflation"
                && dictionary.iter().any(|d| {
                    Guidance::embedded()
                        .for_rule(&d.rule_id)
                        .is_some_and(|g| g.id == "structure.significance-inflation")
                        && d.raw_offset.start < e.raw_offset.end
                        && e.raw_offset.start < d.raw_offset.end
                })
            {
                continue;
            }
            let Some(mut f) = finding(&e.rule_id, e.severity, e.suppression.is_some()) else {
                continue;
            };
            f.location = Some(ReviewLocation {
                line: e.line,
                column: e.column,
                end_line: e.end_line,
                end_column: e.end_column,
                source_ranges: e.source_ranges.clone(),
            });
            f.matched_text = e.matched_text.clone();
            f.suggestion = e.suggestion.clone();
            f.context = e.context.clone();
            let unit_index = units.partition_point(|u| u.prose.start <= e.prose_offset.start);
            if let Some(u) = unit_index
                .checked_sub(1)
                .and_then(|i| units.get(i))
                .filter(|u| e.prose_offset.end <= u.prose.end)
            {
                f.sentence = Some(u.text.clone());
                if e.rule_id == "punctuation.em-dash-density" && u.kind == UnitKind::ListItem {
                    let tail = doc.prose[e.prose_offset.end..u.prose.end]
                        .trim_start()
                        .trim_start_matches('~');
                    f.context = Some(
                        if tail.starts_with('$') || tail.starts_with(char::is_numeric) {
                            "list_separator"
                        } else {
                            "list_item"
                        }
                        .into(),
                    );
                }
            }
            all.push(f);
        }
        for d in &s.document_findings {
            if let Some(mut f) = finding(&d.rule_id, d.severity, d.suppression.is_some()) {
                f.message = Some(d.message.clone());
                f.suggestion = d.suggestion.clone();
                all.push(f);
            }
        }
    }
    all.sort_by_key(|f| {
        (
            f.suppressed,
            f.leverage,
            f.context.as_deref() == Some("list_separator"),
            f.location
                .as_ref()
                .and_then(|l| l.source_ranges.first())
                .map_or(usize::MAX, |r| r.start),
            f.rule_id.clone(),
        )
    });
    let total_findings = all.len();
    let suppressed_findings = all.iter().filter(|f| f.suppressed).count();
    let mut leverage_counts = BTreeMap::new();
    for f in all.iter().filter(|f| !f.suppressed) {
        *leverage_counts.entry(f.leverage).or_insert(0) += 1;
    }
    let active = |id: &str| all.iter().any(|f| !f.suppressed && f.rule_id == id);
    let backend_ready = |name: &str| {
        checks
            .iter()
            .any(|c| c.backend == name && c.status == AnalysisStatus::Completed)
    };
    let suppressed = |id: &str| {
        doc.suppressed_rules.iter().any(|r| r == id)
            || report.settings.ignore_rules.iter().any(|r| r == id)
            || all.iter().any(|f| f.suppressed && f.rule_id == id)
    };
    let rule_check = |id, backend, rule: &str| {
        CheckItem { id,status:if active(rule) { CheckStatus::Fail } else if !backend_ready(backend) || suppressed(rule) { CheckStatus::Unknown } else { CheckStatus::Pass }, detail:"An editing prompt; absence is meaningful only when the check completed and was not suppressed.".into() }
    };
    let mut checklist = vec![
        CheckItem {
            id: "no-tell-vocabulary",
            status: if all
                .iter()
                .any(|f| !f.suppressed && f.category == Category::Vocabulary)
            {
                CheckStatus::Fail
            } else if backend_ready("vocabulary")
                && !doc.suppressed_rules.iter().any(|id| {
                    Guidance::embedded()
                        .for_rule(id)
                        .is_some_and(|g| g.category == Category::Vocabulary)
                })
                && !all
                    .iter()
                    .any(|f| f.suppressed && f.category == Category::Vocabulary)
            {
                CheckStatus::Pass
            } else {
                CheckStatus::Unknown
            },
            detail: "Review word choices in context, including technical exceptions.".into(),
        },
        rule_check(
            "no-em-dash-connectors",
            "punctuation",
            "punctuation.em-dash-density",
        ),
    ];
    let lengths: Vec<_> = units
        .iter()
        .filter(|u| u.kind == UnitKind::Sentence)
        .map(|u| u.words)
        .collect();
    checklist.push(CheckItem{id:"sentence-length-varies",status:if !report.complete || !doc.english_supported() || !backend_ready("structure") || lengths.len()<3 {CheckStatus::Unknown} else if lengths.windows(3).any(|w| w.iter().max().unwrap()-w.iter().min().unwrap()<=6) {CheckStatus::Fail} else {CheckStatus::Pass},detail:"Three sentence lengths within ±3 words are a reading prompt; headings and lists are excluded.".into()});
    checklist.push(CheckItem {
        id: "has-checkable-specific",
        status: if !report.complete {
            CheckStatus::Unknown
        } else if doc.prose.chars().any(|c| c.is_ascii_digit()) {
            CheckStatus::Pass
        } else {
            CheckStatus::Fail
        },
        detail: "A digit-bearing token is a checkable-detail prompt, not verification of a claim."
            .into(),
    });
    checklist.push(CheckItem {
        id: "no-vague-attribution",
        status: if active("studies-show") || active("experts-agree") {
            CheckStatus::Fail
        } else if !backend_ready("vocabulary")
            || suppressed("studies-show")
            || suppressed("experts-agree")
        {
            CheckStatus::Unknown
        } else {
            CheckStatus::Pass
        },
        detail: "Name actual evidence; this check cannot verify sources.".into(),
    });
    checklist.push(CheckItem {
        id: "no-negative-parallelism",
        status: if active("not-just-x-but-y") || active("structure.negative-parallelism") {
            CheckStatus::Fail
        } else if !backend_ready("vocabulary")
            || !backend_ready("structure")
            || suppressed("not-just-x-but-y")
            || suppressed("structure.negative-parallelism")
        {
            CheckStatus::Unknown
        } else {
            CheckStatus::Pass
        },
        detail: "Retain contrasts that clarify a distinction.".into(),
    });
    for (id, detail) in [
        (
            "facts-are-real",
            "confirm every name, number and source is the writer's own",
        ),
        (
            "read-aloud",
            "Read aloud to check clarity and the author's voice.",
        ),
        (
            "tone-shifts",
            "Confirm that changes in tone fit the purpose and audience.",
        ),
    ] {
        checklist.push(CheckItem {
            id,
            status: CheckStatus::Unknown,
            detail: detail.into(),
        });
    }
    checklist.push(rule_check(
        "no-summary-close",
        "structure",
        "structure.summary-close",
    ));
    checklist.push(rule_check(
        "no-rule-of-three",
        "structure",
        "structure.rule-of-three",
    ));
    if doc.words.is_empty() && report.complete {
        for c in &mut checklist {
            c.status = CheckStatus::NotApplicable;
        }
    }
    let mut visible: Vec<_> = all
        .into_iter()
        .filter(|f| f.severity >= report.settings.minimum_severity)
        .collect();
    let omitted_findings = visible.len().saturating_sub(report.settings.display_limit);
    visible.truncate(report.settings.display_limit);
    let (findings, document) = visible.into_iter().partition(|f| f.location.is_some());
    ReviewReport {
        schema_version: "1.0.0",
        review_version: "review-v1",
        path: report.path.clone(),
        guidance_version: Guidance::embedded().guidance_version.clone(),
        complete: report.complete,
        prose_words: report.prose_words,
        leverage_counts,
        findings,
        document,
        checklist,
        checks,
        total_findings,
        suppressed_findings,
        omitted_findings,
        incomplete_reasons: report.incomplete_reasons.clone(),
        hotspots: (!report.settings.models.is_empty()).then(|| {
            let evidence: Vec<_> = report
                .backends
                .iter()
                .filter_map(|b| score(&b.outcome))
                .filter_map(|s| s.model_evidence.as_ref())
                .collect();
            crate::hotspots::rank(doc, &evidence)
        }),
    }
}
pub fn human(report: &ReviewReport) -> String {
    let mut text = format!(
        "{}: advisory review ({} words; {})\nLeverage counts: {:?}\n",
        report.path,
        report.prose_words,
        if report.complete {
            "complete"
        } else {
            "incomplete"
        },
        report.leverage_counts
    );
    let mut leverage = 0;
    let mut ordered: Vec<_> = report.findings.iter().chain(&report.document).collect();
    ordered.sort_by_key(|f| {
        (
            f.suppressed,
            f.leverage,
            f.context.as_deref() == Some("list_separator"),
            f.location
                .as_ref()
                .and_then(|l| l.source_ranges.first())
                .map_or(usize::MAX, |r| r.start),
            f.rule_id.as_str(),
        )
    });
    for f in ordered {
        if leverage != f.leverage {
            leverage = f.leverage;
            let category = match leverage {
                1 => "content",
                2 => "structure",
                3 => "rhythm",
                4 => "punctuation and formatting",
                _ => "vocabulary",
            };
            text.push_str(&format!("\nLeverage {leverage} — {category}\n"));
        }
        let location = f
            .location
            .as_ref()
            .map_or("document".into(), |l| format!("{}:{}", l.line, l.column));
        text.push_str(&format!(
            "{location}: {}{}\n",
            f.rule_id,
            if f.suppressed { " [suppressed]" } else { "" }
        ));
        if f.context.as_deref() == Some("list_separator") {
            text.push_str(&format!("Keep when: {}\n", f.keep_when));
        }
        text.push_str(&format!("Why: {}\nFix: {}\n", f.why, f.fix));
        if f.context.as_deref() != Some("list_separator") {
            text.push_str(&format!("Keep when: {}\n", f.keep_when));
        }
        if let Some(message) = &f.message {
            text.push_str(&format!("{message}\n"));
        }
    }
    for c in &report.checklist {
        text.push_str(&format!(
            "[{}] {}: {}\n",
            serde_json::to_value(c.status).unwrap().as_str().unwrap(),
            c.id,
            c.detail
        ));
    }
    for c in &report.checks {
        if c.status != AnalysisStatus::Completed {
            text.push_str(&format!(
                "{:?}: {}: {}\n",
                c.status,
                c.backend,
                c.reason.as_deref().unwrap_or("")
            ));
        }
    }
    if let Some(h) = &report.hotspots {
        text.push_str(&format!(
            "\n{}\n{}\n",
            h.label,
            if h.validated {
                "[validated editorial utility]"
            } else {
                "[unvalidated diagnostics]"
            }
        ));
        if let Some(reason) = &h.reason {
            text.push_str(&format!("{reason}\n"));
        }
        for spot in &h.hotspots {
            text.push_str(&format!(
                "#{} lines {}–{} ({}): mean z {:+.2}, agreement {}/{}\n",
                spot.rank,
                spot.line,
                spot.end_line,
                spot.heading.as_deref().unwrap_or("unheaded"),
                spot.mean_z,
                spot.agreement,
                spot.per_model.len()
            ));
            for model in &spot.per_model {
                text.push_str(&format!(
                    "  {} rank {}: {:+.4} (z {:+.2})\n",
                    model.backend, model.rank, model.raw_output, model.z
                ));
            }
        }
    }
    for reason in &report.incomplete_reasons {
        text.push_str(&format!("Incomplete: {reason}\n"));
    }
    text
}
