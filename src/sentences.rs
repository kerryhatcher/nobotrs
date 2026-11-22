//! Editorial units, parallel to the frozen statistical sentence segmentation.
use crate::{
    deadline::Deadline,
    document::{BlockKind, Document},
    error::Error,
};
use serde::Serialize;
use std::ops::Range;
use unicode_segmentation::UnicodeSegmentation;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum UnitKind {
    Sentence,
    Heading,
    ListItem,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Boundary {
    Terminal,
    LineBreak,
    BlockEnd,
}
#[derive(Debug, Clone, Serialize)]
pub struct SentenceUnit {
    pub id: usize,
    pub prose: Range<usize>,
    pub source_ranges: Vec<Range<usize>>,
    /// Normalized display text; navigation always uses original UTF-8 source ranges.
    pub text: String,
    pub block: usize,
    pub paragraph: usize,
    pub kind: UnitKind,
    pub boundary: Boundary,
    pub uncertain: bool,
    pub words: usize,
}
pub fn sentence_units(doc: &Document) -> Vec<SentenceUnit> {
    build(doc, None).expect("unbounded editorial units")
}
pub fn sentence_units_with_deadline(
    doc: &Document,
    deadline: Deadline,
) -> Result<Vec<SentenceUnit>, Error> {
    build(doc, Some(deadline))
}
fn build(doc: &Document, deadline: Option<Deadline>) -> Result<Vec<SentenceUnit>, Error> {
    let poll = || {
        if deadline.is_some_and(|d| d.expired()) {
            Err(Error::Timeout)
        } else {
            Ok(())
        }
    };
    poll()?;
    let mut units = Vec::new();
    let mut paragraph = 0;
    let mut previous_block = None;
    for (block, span) in doc.prose_spans.iter().enumerate() {
        poll()?;
        if previous_block != Some(doc.block_ids[block]) {
            paragraph += 1;
        }
        previous_block = Some(doc.block_ids[block]);
        let mut chunks = Vec::new();
        let mut start = span.start;
        let mut offset = span.start;
        let lines: Vec<_> = doc.prose[span.clone()].split_inclusive('\n').collect();
        for (i, line) in lines.iter().enumerate() {
            poll()?;
            let end = offset + line.len();
            let clean = line.trim();
            let next = lines.get(i + 1).map_or("", |l| l.trim());
            let blank = clean.is_empty();
            let list = clean.contains(" — ");
            let next_list = next.contains(" — ");
            let split = blank
                || list
                || next_list
                || clean.ends_with(':')
                || (!clean.ends_with(['.', '!', '?', '"', '”', '’', ')'])
                    && next.chars().next().is_some_and(|c| !c.is_lowercase()));
            if split && end < span.end {
                chunks.push((start..end, Boundary::LineBreak, paragraph));
                start = end;
                if blank {
                    paragraph += 1;
                }
            }
            offset = end;
        }
        chunks.push((start..span.end, Boundary::BlockEnd, paragraph));
        for (chunk, boundary, para) in chunks {
            poll()?;
            let sentences = crate::document::sentence_ranges_bounded(
                &doc.prose,
                std::slice::from_ref(&chunk),
                deadline,
            )?;
            for (n, r) in sentences.iter().enumerate() {
                poll()?;
                let mut range = r.clone();
                // The legacy scanner excludes closing quotes; the editorial index includes them.
                while range.end < chunk.end
                    && doc.prose[range.end..chunk.end].starts_with(['"', '\'', '”', '’', ')', ']'])
                {
                    range.end += doc.prose[range.end..].chars().next().unwrap().len_utf8();
                }
                while range.start < range.end
                    && doc.prose[range.start..range.end].starts_with(char::is_whitespace)
                {
                    range.start += doc.prose[range.start..].chars().next().unwrap().len_utf8();
                }
                while range.end > range.start
                    && doc.prose[range.start..range.end].ends_with(char::is_whitespace)
                {
                    range.end -= doc.prose[..range.end]
                        .chars()
                        .next_back()
                        .unwrap()
                        .len_utf8();
                }
                // The scanner starts the next sentence before the closing quote it omitted.
                while units
                    .last()
                    .is_some_and(|u: &SentenceUnit| range.start < u.prose.end)
                {
                    range.start = units.last().unwrap().prose.end;
                }
                let text = doc.prose[range.clone()].trim().replace('\r', "");
                if text.unicode_words().next().is_none() {
                    continue;
                }
                let end_kind =
                    if n + 1 < sentences.len() || text.ends_with(['.', '!', '?', '”', '"']) {
                        Boundary::Terminal
                    } else {
                        boundary
                    };
                let kind = match doc.block_kinds[block] {
                    BlockKind::Heading => UnitKind::Heading,
                    BlockKind::ListItem => UnitKind::ListItem,
                    _ if text.contains(" — ") => UnitKind::ListItem,
                    _ if end_kind == Boundary::LineBreak => UnitKind::Heading,
                    _ => UnitKind::Sentence,
                };
                let words = text.unicode_words().count();
                units.push(SentenceUnit {
                    id: units.len(),
                    source_ranges: doc.source_ranges(range.clone()),
                    prose: range,
                    text,
                    block: doc.block_ids[block],
                    paragraph: para,
                    kind,
                    boundary: end_kind,
                    uncertain: end_kind == Boundary::LineBreak
                        && words >= 12
                        && kind != UnitKind::ListItem,
                    words,
                });
            }
        }
    }
    poll()?;
    Ok(units)
}
pub fn paragraphs(units: &[SentenceUnit]) -> Vec<Range<usize>> {
    let mut out: Vec<Range<usize>> = vec![];
    for (i, unit) in units.iter().enumerate() {
        if i > 0 && units[i - 1].paragraph == unit.paragraph {
            out.last_mut().unwrap().end = i + 1;
        } else {
            out.push(i..i + 1);
        }
    }
    out
}
#[cfg(test)]
mod tests {
    use super::*;
    fn units(s: &str, md: bool) -> Vec<SentenceUnit> {
        sentence_units(&Document::from_stdin_text(s.into(), md))
    }
    #[test]
    fn decimals_and_quotes() {
        let u = units(
            "FY27 needs 7.8% and 15–20% from Dr. Smith. She said “Still short.” Then left.",
            false,
        );
        assert_eq!(
            u.iter().map(|x| x.text.as_str()).collect::<Vec<_>>(),
            [
                "FY27 needs 7.8% and 15–20% from Dr. Smith.",
                "She said “Still short.”",
                "Then left."
            ]
        );
    }
    #[test]
    fn crlf_wrap_and_paragraphs() {
        let u = units(
            "This sentence wraps\r\nonto a second line.\r\n\r\nNext one.\r\n",
            false,
        );
        assert_eq!(u[0].text, "This sentence wraps\nonto a second line.");
        assert_eq!(paragraphs(&u).len(), 2);
        assert!(u.iter().all(|x| !x.text.contains('\r')));
    }
    #[test]
    fn markdown_ancestry_and_source() {
        let raw = "# Title\n\n- first *item*\n\n  More `code` text.\n  - nested item\n\nA \\*real\\* &amp; [linked](https://example.test) sentence.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n";
        let d = Document::from_stdin_text(raw.into(), true);
        let u = sentence_units(&d);
        assert_eq!(u[0].kind, UnitKind::Heading);
        assert!(u
            .iter()
            .filter(|x| x.text.contains("item")
                || x.text.contains("More")
                || x.text.contains("text."))
            .all(|x| x.kind == UnitKind::ListItem));
        assert_eq!(
            d.block_kinds
                .iter()
                .filter(|&&k| k == BlockKind::TableCell)
                .count(),
            4
        );
        for x in u {
            for r in x.source_ranges {
                assert!(d.raw.get(r).is_some());
            }
        }
    }
    #[test]
    fn bibb_units_and_legacy_segmentation() {
        let d = Document::from_stdin_text(
            include_str!("../evaluation/fixtures/bibb-fy27.txt").into(),
            false,
        );
        let u = sentence_units(&d);
        assert_eq!(d.sentences.len(), 21);
        assert_eq!(u.iter().filter(|x| x.kind == UnitKind::Heading).count(), 4);
        assert_eq!(u.iter().filter(|x| x.kind == UnitKind::ListItem).count(), 9);
        assert!(u.iter().any(|x| x.text == "Still short."));
        for (i, _) in d.prose.match_indices('—') {
            assert_eq!(
                u.iter().find(|x| x.prose.contains(&i)).unwrap().kind,
                UnitKind::ListItem
            );
        }
    }
}
