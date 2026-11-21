use crate::{backend::ScoreOutcome, pipeline::Report, score::Severity};
use serde_json::{json, Value};
pub fn human(report: &Report) -> String {
    let mut out = format!(
        "{}: {:?} ({} prose words; {} participating families; {})\n",
        report.path,
        report.verdict,
        report.prose_words,
        report.families.len(),
        if report.complete {
            "complete"
        } else {
            "incomplete"
        }
    );
    out.push_str(&format!(
        "Language: {} ({})\n",
        report.language.applicability, report.language.reason
    ));
    for b in &report.backends {
        match &b.outcome {
            ScoreOutcome::Scored(s) | ScoreOutcome::Incomplete { score: s, .. } => {
                for (name, m) in &s.metrics {
                    out.push_str(&format!(
                        "  {}: {} = {:.4} {}\n",
                        b.backend, name, m.value, m.unit
                    ));
                }
                if let Some(m) = &s.model_evidence {
                    out.push_str(&format!(
                        "  {}: model evidence (revision {}, tokenizer {}, {} {} {}, raw {:.6} {})\n",
                        b.backend,
                        m.model_revision,
                        m.tokenizer_revision,
                        m.runtime,
                        m.device,
                        m.precision,
                        m.raw_output,
                        m.raw_units
                    ));
                    out.push_str(&format!(
                        "  {}: excerpt {} tokens / limit {} ({:.4} coverage, truncated={}), {} prepared words, {:.1} ms\n",
                        b.backend,
                        m.excerpt_tokens,
                        m.token_limit,
                        m.excerpt_coverage.unwrap_or(0.0),
                        m.truncated,
                        m.prepared_words,
                        m.elapsed_ms
                    ));
                    if let Some(ds) = &m.detectorscope {
                        out.push_str(&format!(
                            "  {}: DetectorScope bias {:.6}, residual {:.3e}, {} active features, omitted {}, remainder {:.6}, filter {:.2}, formatting {}\n",
                            b.backend,
                            ds.bias,
                            ds.reconstruction_residual,
                            ds.active_features,
                            ds.omitted_features,
                            ds.remainder,
                            ds.feature_filter,
                            ds.formatting_profile
                        ));
                        for feature in &ds.top_features {
                            out.push_str(&format!(
                                "    feature {} {:+.6} {}\n",
                                feature.id, feature.contribution, feature.description
                            ));
                        }
                    }
                }
                for f in &s.document_findings {
                    if f.suppression.is_none() {
                        out.push_str(&format!("  document [{}] {}\n", f.rule_id, f.message));
                    }
                }
                for e in &s.evidence {
                    out.push_str(&format!(
                        "  {}:{}:{} [{}] {}{}\n",
                        report.path,
                        e.line,
                        e.column,
                        e.rule_id,
                        e.matched_text,
                        e.suggestion
                            .as_ref()
                            .map(|s| format!(" — {s}"))
                            .unwrap_or_default()
                    ));
                }
            }
            ScoreOutcome::Abstained { reason, .. } => {
                out.push_str(&format!("  {}: abstained ({reason})\n", b.backend))
            }
            ScoreOutcome::Failed(e) => out.push_str(&format!("  {}: failed ({e})\n", b.backend)),
        }
    }
    if report.omitted_findings > 0 {
        out.push_str(&format!(
            "  {} findings omitted from display; policy used all {} findings\n",
            report.omitted_findings, report.effective_finding_count
        ));
    }
    for reason in &report.incomplete_reasons {
        out.push_str(&format!("  incomplete: {reason}\n"));
    }
    out
}
pub fn sarif(reports: &[Report]) -> Value {
    let mut results = vec![];
    let mut notices = vec![];
    for report in reports {
        for reason in &report.incomplete_reasons {
            notices.push(
                json!({"level":"error","message":{"text":format!("{}: {reason}",report.path)}}),
            );
        }
        for b in &report.backends {
            if let ScoreOutcome::Scored(s) | ScoreOutcome::Incomplete { score: s, .. } = &b.outcome
            {
                for f in &s.document_findings {
                    let mut value = json!({"ruleId":f.rule_id,"level":severity_level(f.severity),"message":{"text":f.message}});
                    if let Some(reason) = &f.suppression {
                        value["suppressions"] = json!([{"kind":"inSource","justification":reason}]);
                    }
                    results.push(value);
                }
                for e in &s.candidates {
                    if e.disposition != "selected" && e.disposition != "suppressed" {
                        continue;
                    }
                    let mut value = json!({"ruleId":e.rule_id,"level":severity_level(e.severity),"message":{"text":e.suggestion.as_ref().map_or_else(||format!("Heuristic writing tell: {}",e.matched_text),Clone::clone)},"locations":[{"physicalLocation":{"artifactLocation":{"uri":uri(&report.path)},"region":{"startLine":e.line,"startColumn":e.column,"endLine":e.end_line,"endColumn":e.end_column}}}],"properties":{"sourceRanges":e.source_ranges,"discontinuous":e.source_ranges.len()>1}});
                    if let Some(reason) = &e.suppression {
                        value["suppressions"] = json!([{"kind":"inSource","justification":reason}]);
                    }
                    results.push(value);
                }
            }
        }
    }
    let dictionary = crate::dictionary::Dictionary::embedded();
    let mut rules:Vec<_>=dictionary.entries.iter().map(|e|json!({"id":e.id,"shortDescription":{"text":format!("Heuristic vocabulary tell: {}",e.id)},"help":{"text":e.notes.as_deref().unwrap_or("Editing prompt only; not an authorship determination.")},"defaultConfiguration":{"level":severity_level(Severity::Medium)},"properties":{"category":e.category,"pattern":e.pattern,"source":e.source}})).collect();
    rules.extend([json!({"id":"punctuation.em-dash-density","shortDescription":{"text":"Em dash density"},"defaultConfiguration":{"level":severity_level(Severity::Medium)}}),json!({"id":"statistics.burstiness","shortDescription":{"text":"Document-wide sentence length variation"},"defaultConfiguration":{"level":severity_level(Severity::Low)}})]);
    json!({"version":"2.1.0","$schema":"https://json.schemastore.org/sarif-2.1.0.json","runs":[{"tool":{"driver":{"name":"nobotrs","version":env!("CARGO_PKG_VERSION"),"rules":rules,"informationUri":"https://github.com/kerryhatcher/nobotrs"}},"results":results,"columnKind":"unicodeCodePoints","invocations":[{"executionSuccessful":reports.iter().all(|r|r.complete),"toolExecutionNotifications":notices}],"properties":{"displayTruncated":reports.iter().any(|r|r.omitted_candidates>0 || r.omitted_document_findings>0),"uncalibrated":true}}]})
}
fn severity_level(severity: Severity) -> &'static str {
    match severity {
        Severity::Low => "note",
        Severity::Medium => "warning",
        Severity::High => "error",
    }
}
fn uri(path: &str) -> String {
    let mut out = String::new();
    for b in path.bytes() {
        if b.is_ascii_alphanumeric() || b"/.-_~:".contains(&b) {
            out.push(b as char);
        } else {
            out.push_str(&format!("%{b:02X}"));
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::severity_level;
    use crate::score::Severity;

    #[test]
    fn sarif_severity_mapping_is_explicit() {
        assert_eq!(severity_level(Severity::Low), "note");
        assert_eq!(severity_level(Severity::Medium), "warning");
        assert_eq!(severity_level(Severity::High), "error");
    }
}
