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
            doc.prepare_markdown();
        } else {
            let raw = doc.raw.clone();
            doc.append(&raw, 0..raw.len());
            doc.boundary();
        }
        doc.words = doc
            .prose
            .unicode_word_indices()
            .map(|(i, w)| i..i + w.len())
            .collect();
        doc.sentences = sentence_ranges(&doc.prose, &doc.prose_spans);
        let (mut line, mut col) = (1, 1);
        for (i, c) in doc.raw.char_indices() {
            doc.positions.push((i, line, col));
            if c == '\n' {
                line += 1;
                col = 1;
            } else {
                col += 1;
            }
        }
        doc.positions.push((doc.raw.len(), line, col));
        doc
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
    fn append(&mut self, text: &str, source: Range<usize>) {
        let equal = self.raw.get(source.clone()) == Some(text);
        for (i, c) in text.char_indices() {
            let r = if equal {
                source.start + i..source.start + i + c.len_utf8()
            } else {
                source.clone()
            };
            self.mapping.extend(std::iter::repeat_n(r, c.len_utf8()));
        }
        self.prose.push_str(text);
    }
    fn boundary(&mut self) {
        let start = self.prose_spans.last().map_or(0, |r| r.end + 1);
        if start < self.prose.len() {
            self.prose_spans.push(start..self.prose.len());
            self.prose.push('\n');
            self.mapping.push(0..0);
        }
    }
    fn prepare_markdown(&mut self) {
        // Closed YAML front matter at the start is excluded; malformed blocks remain Markdown.
        let mut offset = 0;
        let mut lines = self.raw.split_inclusive('\n');
        if lines
            .next()
            .is_some_and(|l| l.trim_end_matches(['\r', '\n']) == "---")
        {
            let mut end = self.raw.find('\n').map_or(self.raw.len(), |i| i + 1);
            for line in lines {
                end += line.len();
                if line.trim_end_matches(['\r', '\n']) == "---" {
                    offset = end;
                    break;
                }
            }
        }
        // Own events to allow appending to the prepared document without retaining a borrow.
        let events: Vec<_> = Parser::new_ext(&self.raw[offset..], Options::ENABLE_TABLES)
            .into_offset_iter()
            .map(|(e, r)| (e.into_static(), r.start + offset..r.end + offset))
            .collect();
        let mut excluded = 0usize;
        for (event, range) in events {
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
                Event::Text(text) => self.append(&text, range),
                Event::SoftBreak | Event::HardBreak => self.append(" ", range),
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
    }
}

/// Shared approximate segmentation, including abbreviation/decimal rejection and punctuation runs.
pub fn sentence_ranges(text: &str, blocks: &[Range<usize>]) -> Vec<Range<usize>> {
    let mut out = vec![];
    for block in blocks {
        let mut start = block.start;
        for (relative, c) in text[block.clone()].char_indices() {
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
    out
}

fn containing(ranges: &[Range<usize>], target: &Range<usize>) -> Option<usize> {
    let i = ranges
        .partition_point(|r| r.start <= target.start)
        .checked_sub(1)?;
    (target.end <= ranges[i].end).then_some(i)
}
