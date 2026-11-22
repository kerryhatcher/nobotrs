//! Shared optional full-coverage reporting. Opening evidence stays untouched.
use super::{
    windows::{self, PlanUnit, Window, WindowRun, WindowStatus},
    DetectorScopeEvidence, WindowEvidence,
};
use crate::{
    backend::ScoreOutcome, deadline::Deadline, document::Document, error::Error, score::Score,
    sentences::UnitKind,
};
use std::ops::Range;
use tokenizers::Tokenizer;
#[cfg(feature = "models-encoders")]
pub fn identity_map(text: &str) -> Vec<Range<usize>> {
    text.char_indices()
        .flat_map(|(i, c)| std::iter::repeat_n(i..i + c.len_utf8(), c.len_utf8()))
        .collect()
}
#[cfg(feature = "models-detectorscope")]
pub fn flatten_with_map(text: &str) -> (String, Vec<Range<usize>>) {
    let mut out = String::new();
    let mut map = Vec::new();
    let mut last = None;
    for word in text.split_whitespace() {
        let start = word.as_ptr() as usize - text.as_ptr() as usize;
        if let Some(previous) = last {
            out.push(' ');
            map.push(previous..start);
        }
        for (i, c) in word.char_indices() {
            out.push(c);
            map.extend(std::iter::repeat_n(
                start + i..start + i + c.len_utf8(),
                c.len_utf8(),
            ));
        }
        last = Some(start + word.len());
    }
    (out, map)
}
pub fn plan(
    doc: &Document,
    tokenizer: &Tokenizer,
    text: &str,
    map: &[Range<usize>],
    max: usize,
    deadline: Deadline,
) -> Result<Vec<Window>, Error> {
    if deadline.expired() {
        return Err(Error::Timeout);
    }
    let owned;
    let units = if let Some(u) = &doc.editorial_units {
        u.as_slice()
    } else {
        owned = crate::sentences::sentence_units_with_deadline(doc, deadline)?;
        &owned
    };
    let mut heading = None;
    let mut planned = Vec::new();
    for u in units {
        if deadline.expired() {
            return Err(Error::Timeout);
        }
        if u.kind == UnitKind::Heading {
            heading = Some(u.text.clone());
        }
        let start = map.partition_point(|r| r.end <= u.prose.start);
        let end = map.partition_point(|r| r.start < u.prose.end);
        if start < end {
            planned.push(PlanUnit {
                text: start..end,
                paragraph: u.paragraph,
                heading: heading.clone(),
            });
        }
    }
    let windows = windows::plan_windows(tokenizer, text, &planned, max)?;
    if deadline.expired() {
        return Err(Error::Timeout);
    }
    Ok(windows)
}
pub fn prose_range(map: &[Range<usize>], range: Range<usize>) -> Range<usize> {
    if range.is_empty() {
        return 0..0;
    }
    map[range.start].start..map[range.end - 1].end
}
pub fn finish(
    mut score: Score,
    doc: &Document,
    map: &[Range<usize>],
    windows: &[Window],
    run: WindowRun,
    features: Vec<Option<DetectorScopeEvidence>>,
) -> ScoreOutcome {
    let e = score
        .model_evidence
        .as_mut()
        .expect("opening model evidence");
    e.packing_policy = Some(windows::PACKING_POLICY.into());
    e.aggregation_policy = Some(windows::AGGREGATION_POLICY.into());
    e.full_coverage_output = run.aggregate;
    let coverage = if run.eligible_tokens == 0 {
        0.0
    } else {
        run.covered_tokens as f64 / run.eligible_tokens as f64
    };
    e.token_coverage = Some(coverage);
    for (i, (w, r)) in windows.iter().zip(&run.results).enumerate() {
        let prose = prose_range(map, w.text.clone());
        let (status, error) = match &r.status {
            WindowStatus::Scored => ("scored", None),
            WindowStatus::TimedOut => ("timed_out", Some("analysis deadline exceeded".into())),
            WindowStatus::NotRun => ("not_run", None),
            WindowStatus::Failed(error) => ("failed", Some(error.clone())),
        };
        if r.status != WindowStatus::Scored {
            e.coverage_gaps.push(prose.clone());
        }
        e.windows.push(WindowEvidence {
            index: w.index,
            source_ranges: doc.source_ranges(prose.clone()),
            prose,
            units: w.units.clone(),
            heading: w.heading.clone(),
            body_tokens: w.body_tokens,
            status: status.into(),
            error,
            raw_output: r.raw_output,
            insufficient_context: w.body_tokens < windows::MIN_HOTSPOT_TOKENS,
            detectorscope: features.get(i).cloned().flatten(),
        });
    }
    if run.aggregate.is_some() {
        ScoreOutcome::Scored(score)
    } else {
        let reason = if run
            .results
            .iter()
            .any(|r| matches!(r.status, WindowStatus::TimedOut | WindowStatus::NotRun))
        {
            Error::Timeout
        } else {
            Error::ModelLoadFailed(
                "one or more full-coverage windows failed; inspect window errors".into(),
            )
        };
        ScoreOutcome::Incomplete {
            score,
            reason,
            coverage,
        }
    }
}
pub fn planning_failure(mut score: Score, doc: &Document, error: Error) -> ScoreOutcome {
    if let Some(e) = &mut score.model_evidence {
        e.packing_policy = Some(windows::PACKING_POLICY.into());
        e.aggregation_policy = Some(windows::AGGREGATION_POLICY.into());
        e.token_coverage = Some(0.0);
        e.coverage_gaps = std::iter::once(0..doc.prose.len()).collect();
    }
    ScoreOutcome::Incomplete {
        score,
        reason: error,
        coverage: 0.0,
    }
}
