use crate::{config::Settings, document::Document, score::Score};
use pulldown_cmark::{Event, Parser};
use std::{collections::HashSet, ops::Range};
#[derive(Debug, Clone)]
pub struct Directive {
    pub ids: Vec<String>,
    pub scope: Range<usize>,
    pub reason: String,
}
fn validate_ids(ids: &[String], known: &HashSet<String>) -> Result<(), String> {
    for id in ids {
        if !known.contains(id) {
            return Err(format!("unknown suppressed rule ID: {id}"));
        }
    }
    Ok(())
}
pub fn directives(
    doc: &Document,
    settings: &Settings,
    path: &str,
    known: &HashSet<String>,
) -> Result<Vec<Directive>, String> {
    directives_inner(doc, settings, path, known, None)
}
pub fn directives_with_deadline(
    doc: &Document,
    settings: &Settings,
    path: &str,
    known: &HashSet<String>,
    deadline: crate::deadline::Deadline,
) -> Result<Vec<Directive>, String> {
    directives_inner(doc, settings, path, known, Some(deadline))
}
fn directives_inner(
    doc: &Document,
    settings: &Settings,
    path: &str,
    known: &HashSet<String>,
    deadline: Option<crate::deadline::Deadline>,
) -> Result<Vec<Directive>, String> {
    let poll = || {
        if deadline.is_some_and(|d| d.expired()) {
            Err(crate::error::Error::Timeout.to_string())
        } else {
            Ok(())
        }
    };
    poll()?;
    validate_ids(&settings.ignore_rules, known)?;
    let mut out = vec![Directive {
        ids: settings.ignore_rules.clone(),
        scope: 0..doc.raw.len(),
        reason: "global configuration".into(),
    }];
    for (pattern, ids) in &settings.path_ignores {
        poll()?;
        validate_ids(ids, known)?;
        let pattern = regex::escape(pattern)
            .replace("\\*", ".*")
            .replace("\\?", ".");
        if regex::Regex::new(&format!("^{pattern}$"))
            .map_err(|e| e.to_string())?
            .is_match(path)
        {
            out.push(Directive {
                ids: ids.clone(),
                scope: 0..doc.raw.len(),
                reason: "per-path configuration".into(),
            });
        }
    }
    let mut blocks = Vec::new();
    for block in &doc.prose_spans {
        poll()?;
        let ranges = doc.source_ranges(block.clone());
        if let (Some(first), Some(last)) = (ranges.first(), ranges.last()) {
            blocks.push(first.start..last.end);
        }
    }
    for (event, r) in Parser::new(&doc.raw).into_offset_iter() {
        poll()?;
        let text = match event {
            Event::InlineHtml(t) | Event::Html(t) => t,
            _ => continue,
        };
        let text = text.trim();
        let Some(body) = text
            .strip_prefix("<!--")
            .and_then(|s| s.strip_suffix("-->"))
        else {
            continue;
        };
        let body = body.trim();
        if !body.starts_with("nobotrs-") {
            continue;
        }
        let Some((name, ids)) = body.split_once(char::is_whitespace) else {
            return Err(format!(
                "malformed suppression at line {}",
                doc.location(r.start).0
            ));
        };
        let ids: Vec<_> = ids.split(',').map(|s| s.trim().to_string()).collect();
        validate_ids(&ids, known)?;
        let scope = match name {
            "nobotrs-ignore-file" => 0..doc.raw.len(),
            "nobotrs-ignore-next-line" => {
                let start = doc.raw[r.start..]
                    .find('\n')
                    .map(|i| r.start + i + 1)
                    .unwrap_or(doc.raw.len());
                let end = doc.raw[start..]
                    .find('\n')
                    .map(|i| start + i)
                    .unwrap_or(doc.raw.len());
                start..end
            }
            "nobotrs-ignore-block" => {
                let i = blocks.partition_point(|b| b.end < r.start);
                blocks
                    .get(i)
                    .cloned()
                    .unwrap_or(doc.raw.len()..doc.raw.len())
            }
            _ => return Err(format!("unknown suppression directive: {name}")),
        };
        out.push(Directive {
            ids,
            scope,
            reason: format!("{name} at line {}", doc.location(r.start).0),
        });
    }
    poll()?;
    Ok(out)
}
pub fn apply(
    score: &mut Score,
    directives: &[Directive],
    deadline: crate::deadline::Deadline,
) -> Result<(), crate::error::Error> {
    // Local directives only affect actual occurrences. Document metrics are not recomputed
    // by deleting local text. A whole-file rule ignore can disable a document-wide rule.
    for candidate in &mut score.candidates {
        for directive in directives {
            if deadline.expired() {
                return Err(crate::error::Error::Timeout);
            }
            if directive.ids.contains(&candidate.rule_id)
                && candidate
                    .source_ranges
                    .iter()
                    .all(|r| directive.scope.start <= r.start && r.end <= directive.scope.end)
            {
                candidate.suppression = Some(directive.reason.clone());
                candidate.disposition = "suppressed".into();
                break;
            }
        }
    }
    for finding in &mut score.document_findings {
        for directive in directives {
            if deadline.expired() {
                return Err(crate::error::Error::Timeout);
            }
            if (directive.reason == "global configuration"
                || directive.reason == "per-path configuration"
                || directive.reason.starts_with("nobotrs-ignore-file"))
                && directive.ids.contains(&finding.rule_id)
            {
                finding.suppression = Some(directive.reason.clone());
                score.vote = crate::score::VoteStrength::None;
                break;
            }
        }
    }
    if score.backend == "vocabulary" {
        crate::backends::vocabulary::select_effective(score);
    } else {
        score.evidence = score
            .candidates
            .iter()
            .filter(|c| c.suppression.is_none())
            .cloned()
            .collect();
        if score.backend == "punctuation" {
            let count = score.evidence.len();
            let words = score.metrics.get("prose_words").map_or(0.0, |m| m.value);
            score.vote = if count >= 6 && count as f64 > words / 100.0 {
                crate::score::VoteStrength::Strong
            } else if count >= 3 && count as f64 > words / 150.0 {
                crate::score::VoteStrength::Suspicious
            } else {
                crate::score::VoteStrength::None
            };
            score.metrics.insert(
                "effective_em_dash_count".into(),
                crate::score::Metric {
                    value: count as f64,
                    unit: "occurrences".into(),
                    method: "unsuppressed-occurrences/original-prose-denominator-v1".into(),
                },
            );
            if score.vote == crate::score::VoteStrength::None {
                score.evidence.clear();
                for c in &mut score.candidates {
                    if c.suppression.is_none() {
                        c.disposition = "not_actionable".into();
                    }
                }
            }
        }
    }
    if deadline.expired() {
        return Err(crate::error::Error::Timeout);
    }
    Ok(())
}
