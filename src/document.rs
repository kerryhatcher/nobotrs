use crate::{deadline::Deadline, error::Error};
use pulldown_cmark::{Event, Options, Parser, Tag, TagEnd};
use serde::Serialize;
use std::{ops::Range, path::Path};
use unicode_segmentation::UnicodeSegmentation;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ContentType {
    Markdown,
    PlainText,
}
#[derive(Debug, Clone, Serialize)]
pub struct Language {
    pub applicability: String,
    pub source: String,
    pub language: Option<String>,
    pub reason: String,
}
#[derive(Debug, Clone)]
pub struct Document {
    pub raw: String,
    pub prose: String,
    /// Byte ranges in prepared prose. Matches may not cross these gaps/blocks.
    pub prose_spans: Vec<Range<usize>>,
    pub content_type: ContentType,
    pub words: Vec<Range<usize>>,
    pub sentences: Vec<Range<usize>>,
    pub language: Language,
    mapping: Vec<Range<usize>>,
    positions: Vec<(usize, u32, u32)>,
}
impl Document {
    pub fn from_path(path: &Path) -> std::io::Result<Self> {
        Ok(Self::from_stdin_text(
            std::fs::read_to_string(path)?,
            Self::is_markdown(path),
        ))
    }
    pub fn is_markdown(path: &Path) -> bool {
        path.extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| matches!(e.to_ascii_lowercase().as_str(), "md" | "markdown"))
    }
    pub fn from_stdin_text(raw: String, markdown: bool) -> Self {
        Self::prepare(raw, markdown, None).expect("unbounded preparation cannot time out")
    }
    /// Cooperative preparation; parser/segmentation calls are not preemptible.
    pub fn from_stdin_text_with_deadline(
        raw: String,
        markdown: bool,
        deadline: Deadline,
    ) -> Result<Self, Error> {
        Self::prepare(raw, markdown, Some(deadline))
    }
    fn prepare(raw: String, markdown: bool, deadline: Option<Deadline>) -> Result<Self, Error> {
        poll(deadline)?;
        let mut doc = Self {
            raw,
            prose: String::new(),
            prose_spans: vec![],
            content_type: if markdown {
                ContentType::Markdown
            } else {
                ContentType::PlainText
            },
            words: vec![],
            sentences: vec![],
            language: Language {
                applicability: "unknown".into(),
                source: "policy".into(),
                language: None,
                reason:
                    "no reliable open-set language detector; use --language en to assert English"
                        .into(),
            },
            mapping: vec![],
            positions: vec![],
        };
        if markdown {
            doc.prepare_markdown(deadline)?;
        } else {
            let raw = doc.raw.clone();
            doc.append(&raw, 0..raw.len(), deadline)?;
            doc.boundary();
        }
        for (i, word) in doc.prose.unicode_word_indices() {
            poll(deadline)?;
            doc.words.push(i..i + word.len());
        }
        doc.sentences = sentence_ranges_bounded(&doc.prose, &doc.prose_spans, deadline)?;
        let (mut line, mut col) = (1, 1);
        for (i, c) in doc.raw.char_indices() {
            poll(deadline)?;
            doc.positions.push((i, line, col));
            if c == '\n' {
                line += 1;
                col = 1;
            } else {
                col += 1;
            }
        }
        doc.positions.push((doc.raw.len(), line, col));
        poll(deadline)?;
        Ok(doc)
    }
    pub fn assert_language(&mut self, code: Option<&str>) {
        if let Some(code) = code {
            self.language = Language {
                applicability: if code == "en" {
                    "supported"
                } else {
                    "unsupported"
                }
                .into(),
                source: "user_override".into(),
                language: Some(code.into()),
                reason: "explicit user assertion, not automatic recognition".into(),
            };
        }
    }
    pub fn english_supported(&self) -> bool {
        self.language.applicability == "supported"
    }
    pub fn location(&self, offset: usize) -> (u32, u32) {
        let i = self
            .positions
            .partition_point(|p| p.0 <= offset)
            .saturating_sub(1);
        (self.positions[i].1, self.positions[i].2)
    }
    pub fn source_ranges(&self, range: Range<usize>) -> Vec<Range<usize>> {
        let mut out: Vec<Range<usize>> = vec![];
        for r in &self.mapping[range] {
            if r.is_empty() {
                continue;
            }
            if let Some(last) = out.last_mut() {
                if r.start <= last.end {
                    last.end = last.end.max(r.end);
                    continue;
                }
            }
            out.push(r.clone());
        }
        out
    }
    pub fn finding(
        &self,
        range: Range<usize>,
        id: &str,
        suggestion: Option<String>,
    ) -> crate::score::Evidence {
        let source_ranges = self.source_ranges(range.clone());
        let start = source_ranges.first().map_or(0, |r| r.start);
        let end = source_ranges.last().map_or(start, |r| r.end);
        let (line, column) = self.location(start);
        let (end_line, end_column) = self.location(end);
        crate::score::Evidence {
            rule_id: id.into(),
            raw_offset: start..end,
            source_ranges,
            prose_offset: range.clone(),
            line,
            column,
            end_line,
            end_column,
            sentence_context: containing(&self.sentences, &range),
            block_context: containing(&self.prose_spans, &range),
            matched_text: self.prose[range].into(),
            severity: crate::score::Severity::Medium,
            suggestion,
            disposition: "selected".into(),
            suppression: None,
        }
    }
    fn append(
        &mut self,
        text: &str,
        source: Range<usize>,
        deadline: Option<Deadline>,
    ) -> Result<(), Error> {
        poll(deadline)?;
        let equal = self.raw.get(source.clone()) == Some(text);
        for (i, c) in text.char_indices() {
            poll(deadline)?;
            let r = if equal {
                source.start + i..source.start + i + c.len_utf8()
            } else {
                source.clone()
            };
            self.mapping.extend(std::iter::repeat_n(r, c.len_utf8()));
        }
        self.prose.push_str(text);
        poll(deadline)
    }
    fn boundary(&mut self) {
        let start = self.prose_spans.last().map_or(0, |r| r.end + 1);
        if start < self.prose.len() {
            self.prose_spans.push(start..self.prose.len());
            self.prose.push('\n');
            self.mapping.push(0..0);
        }
    }
    fn prepare_markdown(&mut self, deadline: Option<Deadline>) -> Result<(), Error> {
        poll(deadline)?;
        // Closed YAML front matter at the start is excluded; malformed blocks remain Markdown.
        let mut offset = 0;
        let mut lines = self.raw.split_inclusive('\n');
        if lines
            .next()
            .is_some_and(|l| l.trim_end_matches(['\r', '\n']) == "---")
        {
            let mut end = self.raw.find('\n').map_or(self.raw.len(), |i| i + 1);
            for line in lines {
                poll(deadline)?;
                end += line.len();
                if line.trim_end_matches(['\r', '\n']) == "---" {
                    offset = end;
                    break;
                }
            }
        }
        // Own events to allow appending to the prepared document without retaining a borrow.
        let mut events = Vec::new();
        for (event, range) in
            Parser::new_ext(&self.raw[offset..], Options::ENABLE_TABLES).into_offset_iter()
        {
            poll(deadline)?;
            events.push((
                event.into_static(),
                range.start + offset..range.end + offset,
            ));
        }
        let mut excluded = 0usize;
        for (event, range) in events {
            poll(deadline)?;
            match event {
                Event::Start(Tag::CodeBlock(_) | Tag::Image { .. } | Tag::HtmlBlock) => {
                    self.boundary();
                    excluded += 1;
                }
                Event::End(TagEnd::CodeBlock | TagEnd::Image | TagEnd::HtmlBlock) => {
                    excluded = excluded.saturating_sub(1);
                    self.boundary();
                }
                _ if excluded > 0 => {}
                Event::Text(text) => self.append(&text, range, deadline)?,
                Event::SoftBreak | Event::HardBreak => self.append(" ", range, deadline)?,
                Event::Code(_) => self.boundary(),
                Event::InlineHtml(text) if text.starts_with("<!--") => {} // rendered adjacency
                Event::InlineHtml(_) | Event::Html(_) => self.boundary(),
                Event::Start(Tag::Paragraph | Tag::Heading { .. } | Tag::Item | Tag::TableCell)
                | Event::End(
                    TagEnd::Paragraph | TagEnd::Heading(_) | TagEnd::Item | TagEnd::TableCell,
                )
                | Event::Rule => self.boundary(),
                _ => {}
            }
        }
        self.boundary();
        poll(deadline)
    }
}

fn poll(deadline: Option<Deadline>) -> Result<(), Error> {
    if deadline.is_some_and(|d| d.expired()) {
        Err(Error::Timeout)
    } else {
        Ok(())
    }
}

/// Shared approximate segmentation, including abbreviation/decimal rejection and punctuation runs.
pub fn sentence_ranges(text: &str, blocks: &[Range<usize>]) -> Vec<Range<usize>> {
    sentence_ranges_bounded(text, blocks, None).expect("unbounded segmentation cannot time out")
}
fn sentence_ranges_bounded(
    text: &str,
    blocks: &[Range<usize>],
    deadline: Option<Deadline>,
) -> Result<Vec<Range<usize>>, Error> {
    poll(deadline)?;
    let mut out = vec![];
    for block in blocks {
        poll(deadline)?;
        let mut start = block.start;
        for (relative, c) in text[block.clone()].char_indices() {
            poll(deadline)?;
            let i = block.start + relative;
            if !matches!(c, '.' | '!' | '?') {
                continue;
            }
            let next = text[i + c.len_utf8()..block.end].chars().next();
            if next.is_some_and(|c| matches!(c, '.' | '!' | '?')) {
                continue;
            }
            let before = &text[start..i];
            let token = before
                .split_whitespace()
                .last()
                .unwrap_or("")
                .trim_matches(|c: char| !c.is_alphabetic())
                .to_ascii_lowercase();
            if c == '.'
                && (matches!(
                    token.as_str(),
                    "mr" | "mrs" | "ms" | "dr" | "prof" | "sr" | "jr" | "e.g" | "i.e"
                ) || (token.len() == 1 && token.chars().all(char::is_alphabetic)))
            {
                continue;
            }
            let tail = &text[i + c.len_utf8()..block.end];
            let tail = tail.trim_start_matches(['"', '\'', '”', '’', ')', ']']);
            if !tail.is_empty() && !tail.starts_with(char::is_whitespace) {
                continue;
            }
            let end = i + c.len_utf8();
            if text[start..end].unicode_words().next().is_some() {
                out.push(start..end);
            }
            start = end;
        }
        if text[start..block.end].unicode_words().next().is_some() {
            out.push(start..block.end);
        }
    }
    poll(deadline)?;
    Ok(out)
}

fn containing(ranges: &[Range<usize>], target: &Range<usize>) -> Option<usize> {
    let i = ranges
        .partition_point(|r| r.start <= target.start)
        .checked_sub(1)?;
    (target.end <= ranges[i].end).then_some(i)
}

#[cfg(test)]
mod deadline_tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn expired_preparation_and_segmentation_reject_work() {
        let expired = Deadline::new(Duration::ZERO);
        for markdown in [false, true] {
            assert!(matches!(
                Document::from_stdin_text_with_deadline("Visible prose.".into(), markdown, expired),
                Err(Error::Timeout)
            ));
        }
        let text = "Visible prose.";
        let blocks = std::iter::once(0..text.len()).collect::<Vec<_>>();
        assert_eq!(
            sentence_ranges_bounded(text, &blocks, Some(expired)),
            Err(Error::Timeout)
        );
        let mut doc = Document::from_stdin_text(String::new(), false);
        assert_eq!(doc.append(text, 0..0, Some(expired)), Err(Error::Timeout));
        assert!(doc.prose.is_empty());
        assert_eq!(doc.prepare_markdown(Some(expired)), Err(Error::Timeout));
    }

    #[test]
    fn bounded_preparation_preserves_prose_and_source_mapping() {
        let text = "---\r\nx: hidden\r\n---\r\n# Héllo\r\n\r\nExperts *agree* &mdash; yes.\r\nNext sentence!\r\n\r\n````\r\nignored\r\n````\r\n";
        for markdown in [false, true] {
            let reference = Document::from_stdin_text(text.into(), markdown);
            let actual = Document::from_stdin_text_with_deadline(
                text.into(),
                markdown,
                Deadline::new(Duration::from_secs(5)),
            )
            .unwrap();
            assert_eq!(actual.prose, reference.prose);
            assert_eq!(actual.words, reference.words);
            assert_eq!(actual.sentences, reference.sentences);
            assert_eq!(actual.prose_spans, reference.prose_spans);
            assert_eq!(actual.mapping, reference.mapping);
            assert_eq!(actual.positions, reference.positions);
        }
    }
}
