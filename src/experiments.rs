//! Development-only scoring candidates. The default policy uses none of these.
use crate::{
    backend::ScoreOutcome,
    backends::{burstiness::Burstiness, punctuation::Punctuation},
    deadline::Deadline,
    document::{BlockKind, Document},
    sentences::sentence_units_with_deadline,
};
use std::{collections::BTreeSet, ops::Range};

pub const IDS: &[&str] = &[
    "burstiness-units",
    "punctuation-skip-list-separators",
    "structure-votes",
];

pub fn burstiness(doc: &Document, deadline: Deadline) -> ScoreOutcome {
    match sentence_units_with_deadline(doc, deadline) {
        Ok(units) => {
            let ranges: Vec<Range<usize>> = units.into_iter().map(|u| u.prose).collect();
            Burstiness.score_ranges(doc, deadline, &ranges)
        }
        Err(e) => ScoreOutcome::Failed(e),
    }
}

pub fn punctuation(doc: &Document, deadline: Deadline, cap: usize) -> ScoreOutcome {
    let mut separators = BTreeSet::new();
    // A parallel run of label/value lines or an actual Markdown list item can
    // have a separator. Paired dashes within a sentence remain punctuation.
    for (idx, span) in doc.prose_spans.iter().enumerate() {
        let lines: Vec<_> = doc.prose[span.clone()].split_inclusive('\n').collect();
        let mut start = span.start;
        for (i, line) in lines.iter().enumerate() {
            if deadline.expired() {
                return ScoreOutcome::Failed(crate::error::Error::Timeout);
            }
            if let Some((label, value)) = line.split_once(" — ") {
                let parallel = i
                    .checked_sub(1)
                    .and_then(|j| lines.get(j))
                    .is_some_and(|l| l.contains(" — "))
                    || lines.get(i + 1).is_some_and(|l| l.contains(" — "));
                if (parallel || doc.block_kinds[idx] == BlockKind::ListItem)
                    && !label.trim().is_empty()
                    && !value.trim().is_empty()
                    && !value.contains('—')
                {
                    separators.insert(start + label.len() + 1);
                }
            }
            start += line.len();
        }
    }
    Punctuation.score_excluding(doc, deadline, cap, &separators)
}
