//! Align optional local-model sections without using model scores to choose matches.
use nobotrs::{backend::ScoreOutcome, document::Document, pipeline::Report, sentences::UnitKind};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use unicode_segmentation::UnicodeSegmentation;

#[derive(Default)]
pub(super) struct Section {
    heading: Option<String>,
    lines: (u32, u32),
    shingles: BTreeSet<String>,
    z_sum: f64,
    z_weight: usize,
}
impl Section {
    fn mean(&self) -> Option<f64> {
        (self.z_weight > 0).then(|| self.z_sum / self.z_weight as f64)
    }
}
#[derive(Serialize)]
pub(super) struct Delta {
    pub heading: Option<String>,
    pub before_lines: Option<(u32, u32)>,
    pub after_lines: Option<(u32, u32)>,
    pub before_mean_z: Option<f64>,
    pub after_mean_z: Option<f64>,
    pub status: &'static str,
}
fn shingles(text: &str) -> BTreeSet<String> {
    let words: Vec<_> = text.unicode_words().map(str::to_lowercase).collect();
    if words.is_empty() {
        return BTreeSet::new();
    }
    words
        .windows(3.min(words.len()))
        .map(|w| w.join(" "))
        .collect()
}
pub(super) fn collect(report: &Report, doc: &Document) -> (Vec<Section>, BTreeMap<String, f64>) {
    let Some(units) = doc.editorial_units.as_ref() else {
        return Default::default();
    };
    let mut outputs = BTreeMap::new();
    let mut sections: Vec<Section> = Vec::new();
    let mut unit_sections = Vec::new();
    let scored: Vec<_> = report
        .backends
        .iter()
        .filter_map(|b| match &b.outcome {
            ScoreOutcome::Scored(s) => s.model_evidence.as_ref().filter(|m| !m.windows.is_empty()),
            _ => None,
        })
        .collect();
    for unit in units {
        let Some(first) = unit.source_ranges.first() else {
            return Default::default();
        };
        let last = unit.source_ranges.last().unwrap();
        let heading = unit.kind == UnitKind::Heading;
        if sections.is_empty() || heading {
            sections.push(Section {
                heading: heading.then(|| unit.text.clone()),
                lines: (doc.location(first.start).0, doc.location(last.end).0),
                ..Default::default()
            });
        }
        let i = sections.len() - 1;
        sections[i].lines.1 = doc.location(last.end).0;
        if !heading {
            sections[i].shingles.extend(shingles(&unit.text));
        }
        unit_sections.push(i);
    }
    for evidence in scored {
        if let Some(v) = evidence.full_coverage_output {
            outputs.insert(evidence.backend.clone(), v);
        }
        let usable: Vec<_> = evidence
            .windows
            .iter()
            .filter(|w| !w.insufficient_context)
            .filter_map(|w| Some((w, w.raw_output?)))
            .collect();
        if usable.len() < 2 {
            continue;
        }
        let mean = usable.iter().map(|(_, v)| v).sum::<f64>() / usable.len() as f64;
        let sd = (usable.iter().map(|(_, v)| (v - mean).powi(2)).sum::<f64>()
            / usable.len() as f64)
            .sqrt();
        if sd <= f64::EPSILON {
            continue;
        }
        for (window, v) in usable {
            if let Some(i) = unit_sections.get(window.units.start) {
                sections[*i].z_sum += (v - mean) / sd * window.body_tokens as f64;
                sections[*i].z_weight += window.body_tokens;
            }
        }
    }
    (sections, outputs)
}
pub(super) fn align(
    before: &[Section],
    after: &[Section],
    deadline: nobotrs::deadline::Deadline,
) -> Result<Vec<Delta>, String> {
    let mut remaining: BTreeSet<_> = (0..after.len()).collect();
    let mut matches = vec![None; before.len()];
    // Reserve exact titles first, so a similar renamed passage cannot steal a section.
    let mut by_heading = BTreeMap::<&str, std::collections::VecDeque<usize>>::new();
    for (i, s) in after.iter().enumerate() {
        if let Some(h) = &s.heading {
            by_heading.entry(h).or_default().push_back(i);
        }
    }
    for (i, s) in before.iter().enumerate() {
        if let Some(j) = s
            .heading
            .as_deref()
            .and_then(|h| by_heading.get_mut(h))
            .and_then(|q| q.pop_front())
        {
            matches[i] = Some(j);
            remaining.remove(&j);
        }
    }
    for (i, s) in before.iter().enumerate() {
        if matches[i].is_some() || s.shingles.is_empty() {
            continue;
        }
        let mut best = None;
        let mut best_score = 0.0;
        for &j in &remaining {
            if deadline.expired() {
                return Err("section comparison timed out".into());
            }
            let common = s.shingles.intersection(&after[j].shingles).count();
            let union = s.shingles.len() + after[j].shingles.len() - common;
            let score = common as f64 / union as f64;
            if score >= 0.3 && score > best_score {
                best = Some(j);
                best_score = score;
            }
        }
        if let Some(j) = best {
            matches[i] = best;
            remaining.remove(&j);
        }
    }
    let mut results = Vec::new();
    let mut emit = |l: Option<&Section>, r: Option<&Section>, status| {
        results.push(Delta {
            heading: r
                .and_then(|s| s.heading.clone())
                .or_else(|| l.and_then(|s| s.heading.clone())),
            before_lines: l.map(|s| s.lines),
            after_lines: r.map(|s| s.lines),
            before_mean_z: l.and_then(Section::mean),
            after_mean_z: r.and_then(Section::mean),
            status,
        });
    };
    for (left, right) in before.iter().zip(matches) {
        emit(
            Some(left),
            right.map(|j| &after[j]),
            if right.is_some() {
                "matched"
            } else {
                "removed"
            },
        );
    }
    for j in remaining {
        emit(None, Some(&after[j]), "added");
    }
    Ok(results)
}
#[cfg(test)]
mod tests {
    use super::*;
    fn section(name: Option<&str>, body: &str) -> Section {
        Section {
            heading: name.map(str::to_owned),
            shingles: shingles(body),
            ..Default::default()
        }
    }
    #[test]
    fn matches_content_without_stealing_exact_titles() {
        let left = [
            section(Some("Old"), "the square opens on Friday"),
            section(Some("Dates"), "the date is set"),
            section(None, "dozens of books arrived"),
            section(Some("Cost"), "the new library cost money"),
        ];
        let right = [
            section(Some("Hours"), "the square opens on Friday"),
            section(Some("Dates"), "another text"),
            section(None, "dozens of books arrived"),
            section(Some("Donor"), "everyone signed the register"),
        ];
        let ds = align(
            &left,
            &right,
            nobotrs::deadline::Deadline::new(std::time::Duration::from_secs(1)),
        )
        .unwrap();
        assert_eq!(
            ds.iter().map(|s| s.status).collect::<Vec<_>>(),
            ["matched", "matched", "matched", "removed", "added"]
        );
    }
}
