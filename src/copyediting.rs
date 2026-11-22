//! Small offline English editing checks. All positions point into the original input.
use crate::{
    backends::readability::count_syllables,
    deadline::Deadline,
    document::{ContentType, Document},
    sentences::{paragraphs, sentence_units_with_deadline, UnitKind},
};
use pulldown_cmark::{Event, Options, Parser, Tag};
use regex::Regex;
use serde::Serialize;
use std::{collections::HashSet, ops::Range, sync::LazyLock};
use unicode_segmentation::UnicodeSegmentation;

pub const RULE_IDS: &[&str] = &[
    "format.heading-depth",
    "format.list-marker",
    "grammar.adjacent-articles",
    "grammar.article-agreement",
    "style.regional-spelling",
    "spelling.common-typo",
    "complexity.long-clause-chain",
    "readability.dense-passage",
];

#[derive(Debug, Serialize)]
pub struct CopyeditIssue {
    pub rule_id: &'static str,
    pub category: &'static str,
    pub line: u32,
    pub column: u32,
    pub end_line: u32,
    pub end_column: u32,
    pub source_ranges: Vec<Range<usize>>,
    pub matched_text: String,
    pub fix: String,
}

static ARTICLES: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)\b(?:a|an|the)[ \t]+(?:a|an|the)\b").unwrap());
static WRONG_ARTICLE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\b(?:an[ \t]+(?:policy|report|budget|document|user)|a[ \t]+(?:estimate|article|error|hour))\b").unwrap()
});
static QUOTES: LazyLock<Regex> = LazyLock::new(|| Regex::new(r#"“[^”]*”|"[^"]*""#).unwrap());

fn spelling(word: &str) -> Option<&'static str> {
    Some(match word {
        "teh" => "the",
        "recieved" => "received",
        "recieve" => "receive",
        "seperate" => "separate",
        "occured" => "occurred",
        "occurence" => "occurrence",
        "definately" => "definitely",
        "accomodate" => "accommodate",
        "adress" => "address",
        "untill" => "until",
        "goverment" => "government",
        "publically" => "publicly",
        "writting" => "writing",
        "enviroment" => "environment",
        "begining" => "beginning",
        "neccessary" => "necessary",
        _ => return None,
    })
}

struct Check<'a> {
    doc: &'a Document,
    issues: Vec<CopyeditIssue>,
    protected: Vec<Range<usize>>,
    limit: usize,
    deadline: Deadline,
}
impl Check<'_> {
    fn report(
        &mut self,
        rule_id: &'static str,
        category: &'static str,
        ranges: Vec<Range<usize>>,
        fix: String,
    ) -> Result<(), String> {
        let (Some(first), Some(last)) = (ranges.first(), ranges.last()) else {
            return Ok(());
        };
        if self.deadline.expired() {
            return Err("copyediting timed out".into());
        }
        let i = self.protected.partition_point(|r| r.end <= first.start);
        if self.protected.get(i).is_some_and(|r| r.start < last.end) {
            return Ok(());
        }
        if self.issues.len() >= self.limit {
            return Err("copyediting candidate limit exceeded".into());
        }
        let (line, column) = self.doc.location(first.start);
        let (end_line, end_column) = self.doc.location(last.end);
        let matched_text = ranges
            .iter()
            .map(|r| &self.doc.raw[r.clone()])
            .collect::<Vec<_>>()
            .join("");
        self.issues.push(CopyeditIssue {
            rule_id,
            category,
            line,
            column,
            end_line,
            end_column,
            source_ranges: ranges,
            matched_text,
            fix,
        });
        Ok(())
    }
}

pub fn check(
    doc: &Document,
    dialect: &str,
    allowed: &[String],
    limit: usize,
    deadline: Deadline,
) -> Result<Vec<CopyeditIssue>, String> {
    if !doc.english_supported() {
        return Ok(Vec::new());
    }
    let dialect = dialect.to_ascii_lowercase();
    if !matches!(dialect.as_str(), "american" | "british" | "en-us" | "en-gb") {
        return Err("unsupported English dialect".into());
    }
    let mut protected: Vec<_> = QUOTES.find_iter(&doc.raw).map(|h| h.range()).collect();
    let mut headings = Vec::new();
    let mut bullet_changes = Vec::new();
    let mut previous_bullet = None;
    let mut previous = 0;
    if matches!(doc.content_type, ContentType::Markdown) {
        for (event, span) in Parser::new_ext(&doc.raw, Options::ENABLE_TABLES).into_offset_iter() {
            if deadline.expired() {
                return Err("copyediting timed out".into());
            }
            match event {
                Event::Start(Tag::BlockQuote(_) | Tag::CodeBlock(_)) | Event::Code(_) => {
                    protected.push(span)
                }
                Event::Start(Tag::Item) => {
                    let marker = doc.raw.as_bytes()[span.start];
                    if matches!(marker, b'-' | b'*' | b'+') {
                        let (line, col) = doc.location(span.start);
                        if let Some((last_line, last_col, last_marker)) = previous_bullet {
                            if last_line + 1 == line && last_col == col && last_marker != marker {
                                bullet_changes.push(span.start..span.start + 1);
                            }
                        }
                        previous_bullet = Some((line, col, marker));
                    }
                }
                Event::Start(Tag::Heading { level, .. }) => {
                    let depth = level as u8;
                    if previous != 0 && depth > previous + 1 {
                        headings.push((span, previous, depth));
                    }
                    previous = depth;
                }
                _ => {}
            }
        }
    }
    protected.sort_by_key(|r| r.start);
    let mut merged: Vec<Range<usize>> = vec![];
    for range in protected {
        if let Some(last) = merged.last_mut() {
            if range.start <= last.end {
                last.end = last.end.max(range.end);
                continue;
            }
        }
        merged.push(range);
    }
    let mut c = Check {
        doc,
        issues: vec![],
        protected: merged,
        limit,
        deadline,
    };
    for (span, from, to) in headings {
        c.report(
            "format.heading-depth",
            "formatting",
            std::iter::once(span).collect(),
            format!(
                "This heading jumps from level {from} to {to}. Check its place in the outline."
            ),
        )?;
    }
    for marker in bullet_changes {
        c.report("format.list-marker","formatting",std::iter::once(marker).collect(),
            "Adjacent items at the same indentation use different bullet markers. Use a consistent marker if they belong to one list.".into())?;
    }
    let allowed: HashSet<_> = allowed.iter().map(|w| w.to_lowercase()).collect();
    for span in &doc.prose_spans {
        if deadline.expired() {
            return Err("copyediting timed out".into());
        }
        let text = &doc.prose[span.clone()];
        for hit in ARTICLES.find_iter(text) {
            c.report(
                "grammar.adjacent-articles",
                "grammar",
                doc.source_ranges(span.start + hit.start()..span.start + hit.end()),
                "Choose the article that belongs before the noun and remove the extra one.".into(),
            )?;
        }
        for hit in WRONG_ARTICLE.find_iter(text) {
            c.report(
                "grammar.article-agreement",
                "grammar",
                doc.source_ranges(span.start + hit.start()..span.start + hit.end()),
                "Choose “a” or “an” to match the next word’s initial sound.".into(),
            )?;
        }
        for (start, word) in text.unicode_word_indices() {
            if deadline.expired() {
                return Err("copyediting timed out".into());
            }
            let lower = word.to_lowercase();
            if allowed.contains(&lower)
                || word.len() > 1 && word.chars().all(|ch| ch.is_uppercase())
            {
                continue;
            }
            let range = span.start + start..span.start + start + word.len();
            let preferred = match (dialect.as_str(), lower.as_str()) {
                ("american" | "en-us", "colour") => Some("color"),
                ("american" | "en-us", "centre") => Some("center"),
                ("british" | "en-gb", "color") => Some("colour"),
                ("british" | "en-gb", "center") => Some("centre"),
                _ => None,
            };
            if let Some(form) = preferred {
                c.report("style.regional-spelling","style",doc.source_ranges(range.clone()),format!("For the selected dialect, consider “{form}”. Keep the original spelling in names and titles."))?;
            }
            if let Some(replacement) = spelling(&lower) {
                c.report(
                    "spelling.common-typo",
                    "spelling",
                    doc.source_ranges(range),
                    format!("Check the spelling of “{word}”. The usual form is “{replacement}”."),
                )?;
            }
        }
    }
    let prepared;
    let units = if let Some(units) = &doc.editorial_units {
        units
    } else {
        prepared = sentence_units_with_deadline(doc, deadline).map_err(|e| e.to_string())?;
        &prepared
    };
    for unit in units {
        if unit.kind == UnitKind::Sentence
            && unit.words >= 40
            && unit.text.matches([',', ';']).count() >= 3
        {
            c.report("complexity.long-clause-chain","complexity",unit.source_ranges.clone(),format!("This sentence has {} words and several clause breaks. Put its main action first and consider separating the conditions.",unit.words))?;
        }
    }
    for para in paragraphs(units) {
        let paragraph = &units[para];
        if paragraph.iter().any(|u| u.kind != UnitKind::Sentence) {
            continue;
        }
        let words: usize = paragraph.iter().map(|u| u.words).sum();
        if words < 150 || paragraph.len() < 3 {
            continue;
        }
        let syllables: usize = paragraph
            .iter()
            .flat_map(|u| u.text.unicode_words())
            .map(count_syllables)
            .sum();
        let grade = 0.39 * words as f64 / paragraph.len() as f64
            + 11.8 * syllables as f64 / words as f64
            - 15.59;
        if grade >= 13.0 {
            let ranges = paragraph
                .iter()
                .flat_map(|u| u.source_ranges.clone())
                .collect();
            c.report("readability.dense-passage","readability",ranges,format!("Estimated Flesch–Kincaid grade {grade:.1} across {words} words. Check technical terms and sentence length against your reader’s background."))?;
        }
    }
    c.issues.sort_by_key(|f| (f.line, f.column, f.rule_id));
    Ok(c.issues)
}
