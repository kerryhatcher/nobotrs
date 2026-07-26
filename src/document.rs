// src/document.rs
use std::ops::Range;
use std::path::Path;

#[allow(dead_code)] // Temporary: consumed starting in Task 5 (DetectorBackend)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContentType {
    Markdown,
    PlainText,
    #[allow(dead_code)] // Reserved: selected once non-text/non-markdown detection lands
    Unknown,
}

#[allow(dead_code)] // Temporary: consumed starting in Task 5 (DetectorBackend)
#[derive(Debug, Clone)]
pub struct Document {
    pub raw: String,
    pub prose_spans: Vec<Range<usize>>,
    pub content_type: ContentType,
}

impl Document {
    #[allow(dead_code)] // Temporary: consumed starting in Task 5 (DetectorBackend)
    pub fn from_path(path: &Path) -> std::io::Result<Document> {
        let raw = std::fs::read_to_string(path)?;
        let is_markdown = matches!(
            path.extension()
                .and_then(|e| e.to_str())
                .map(|e| e.to_ascii_lowercase())
                .as_deref(),
            Some("md") | Some("markdown")
        );
        Ok(Self::build(raw, is_markdown))
    }

    /// `markdown_hint` mirrors the CLI's `--markdown` flag for stdin (`-`),
    /// where no file extension exists to infer content type from (spec §2.1:
    /// stdin defaults to PlainText unless `--markdown` is passed explicitly).
    #[allow(dead_code)] // Temporary: consumed starting in Task 5 (DetectorBackend)
    pub fn from_stdin_text(raw: String, markdown_hint: bool) -> Document {
        Self::build(raw, markdown_hint)
    }

    fn build(raw: String, is_markdown: bool) -> Document {
        if is_markdown {
            let prose_spans = markdown_prose_spans(&raw);
            Document {
                raw,
                prose_spans,
                content_type: ContentType::Markdown,
            }
        } else {
            let len = raw.len();
            // Intentional: this is a one-element Vec<Range<usize>>, not a
            // range to iterate — clippy's collect-suggestion would change
            // the type to Vec<usize> and is wrong here.
            #[allow(clippy::single_range_in_vec_init)]
            let prose_spans = vec![0..len];
            Document {
                raw,
                prose_spans,
                content_type: ContentType::PlainText,
            }
        }
    }
}

/// Splits `s` into line ranges. Each range includes the line's trailing `\n`
/// (if any); the final line, when the string doesn't end in `\n`, extends to
/// `s.len()` with no newline included. Ranges are byte offsets into `s`.
fn line_spans(s: &str) -> Vec<Range<usize>> {
    let mut spans = Vec::new();
    let len = s.len();
    let mut pos = 0usize;
    while pos < len {
        match s[pos..].find('\n') {
            Some(rel) => {
                let end = pos + rel + 1;
                spans.push(pos..end);
                pos = end;
            }
            None => {
                spans.push(pos..len);
                break;
            }
        }
    }
    spans
}

/// Strips a single trailing `\n` (and a preceding `\r`, for CRLF input) from
/// a line slice produced by `line_spans`, leaving just the line's content.
fn line_content(line: &str) -> &str {
    let s = line.strip_suffix('\n').unwrap_or(line);
    s.strip_suffix('\r').unwrap_or(s)
}

/// Computes prose-only byte ranges of `raw`, excluding fenced code blocks
/// (``` or ~~~ delimited) and a leading YAML front-matter block (--- delimited,
/// only recognized at byte offset 0, i.e. as the very first line). Computed
/// once at `Document::build` time and stored on `Document::prose_spans`
/// (spec §2.1) — never recomputed per backend.
fn markdown_prose_spans(raw: &str) -> Vec<Range<usize>> {
    let lines = line_spans(raw);

    let mut start_idx = 0usize;
    let mut prose_start = 0usize;

    // Front matter: only recognized if the very first line is exactly "---".
    // If found, look for the next line that is also exactly "---" to close
    // the block; the entire front-matter block (both fences and everything
    // between) is excluded from prose. An unterminated opening "---" is not
    // treated as front matter at all.
    if let Some(first) = lines.first() {
        if line_content(&raw[first.clone()]) == "---" {
            for (j, line) in lines.iter().enumerate().skip(1) {
                if line_content(&raw[line.clone()]) == "---" {
                    prose_start = line.end;
                    start_idx = j + 1;
                    break;
                }
            }
        }
    }

    let mut spans = Vec::new();
    let mut in_fence = false;
    let mut fence_marker = "";

    for line in &lines[start_idx..] {
        let content = line_content(&raw[line.clone()]);
        if !in_fence {
            // Opening a fence follows standard markdown syntax: the marker
            // may be followed by an info string (e.g. "```rust").
            let trimmed_start = content.trim_start();
            let is_open_line =
                trimmed_start.starts_with("```") || trimmed_start.starts_with("~~~");
            if is_open_line {
                let marker = if trimmed_start.starts_with("```") {
                    "```"
                } else {
                    "~~~"
                };
                if line.start > prose_start {
                    spans.push(prose_start..line.start);
                }
                in_fence = true;
                fence_marker = marker;
            }
        } else {
            // Closing a fence requires the line, once trimmed of
            // surrounding whitespace, to be *exactly* the same marker —
            // not merely start with it. Otherwise a line like "```extra"
            // appearing inside a fenced block (e.g. a doc demonstrating
            // fence syntax) would prematurely close the fence.
            if content.trim() == fence_marker {
                in_fence = false;
                prose_start = line.end;
            }
        }
    }

    if !in_fence && prose_start < raw.len() {
        spans.push(prose_start..raw.len());
    }

    spans
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plain_text_has_one_prose_span_covering_whole_file() {
        let doc = Document::from_stdin_text("hello world".to_string(), false);
        assert_eq!(doc.content_type, ContentType::PlainText);
        assert_eq!(doc.prose_spans, vec![0..11]);
    }

    #[test]
    fn markdown_excludes_fenced_code_block() {
        let raw = "Intro text.\n\n```rust\nfn code() {}\n```\n\nOutro text.".to_string();
        let doc = Document::from_stdin_text(raw.clone(), true);
        assert_eq!(doc.content_type, ContentType::Markdown);
        // the fenced block (from the opening ``` line through the closing ```
        // line, inclusive) must not be covered by any prose span
        let fence_start = raw.find("```rust").unwrap();
        let fence_end = raw.rfind("```").unwrap() + 3;
        for span in &doc.prose_spans {
            let overlaps = span.start < fence_end && fence_start < span.end;
            assert!(!overlaps, "prose span {:?} overlaps code fence [{fence_start}..{fence_end}]", span);
        }
        // but the intro and outro text are still covered by *some* prose span
        let intro_pos = raw.find("Intro text.").unwrap();
        let outro_pos = raw.find("Outro text.").unwrap();
        assert!(doc.prose_spans.iter().any(|s| s.start <= intro_pos && intro_pos < s.end));
        assert!(doc.prose_spans.iter().any(|s| s.start <= outro_pos && outro_pos < s.end));
    }

    #[test]
    fn markdown_excludes_front_matter() {
        let raw = "---\ntitle: test\n---\n\nBody text.".to_string();
        let doc = Document::from_stdin_text(raw.clone(), true);
        let body_pos = raw.find("Body text.").unwrap();
        assert!(doc.prose_spans.iter().any(|s| s.start <= body_pos && body_pos < s.end));
        assert!(!doc.prose_spans.iter().any(|s| s.start == 0));
    }

    #[test]
    fn markdown_fence_closing_requires_exact_marker_line() {
        // Regression test: a line inside a fence that merely *starts with*
        // the marker (e.g. "```extra", such as a doc demonstrating fence
        // syntax) must not prematurely close the fence. Only the real
        // closing "```" line should end it.
        let raw = "```\nsome code\n```extra\nmore code that should still be in fence\n```\n"
            .to_string();
        let doc = Document::from_stdin_text(raw.clone(), true);
        assert_eq!(doc.content_type, ContentType::Markdown);
        let still_in_fence_pos = raw.find("more code that should still be in fence").unwrap();
        assert!(
            !doc
                .prose_spans
                .iter()
                .any(|s| s.start <= still_in_fence_pos && still_in_fence_pos < s.end),
            "line inside fence was incorrectly classified as prose: {:?}",
            doc.prose_spans
        );
    }

    #[test]
    fn markdown_tilde_fence_closing_requires_exact_marker_line() {
        // Symmetric case for the "~~~" fence delimiter.
        let raw = "~~~\nsome code\n~~~extra\nmore code that should still be in fence\n~~~\n"
            .to_string();
        let doc = Document::from_stdin_text(raw.clone(), true);
        assert_eq!(doc.content_type, ContentType::Markdown);
        let still_in_fence_pos = raw.find("more code that should still be in fence").unwrap();
        assert!(
            !doc
                .prose_spans
                .iter()
                .any(|s| s.start <= still_in_fence_pos && still_in_fence_pos < s.end),
            "line inside fence was incorrectly classified as prose: {:?}",
            doc.prose_spans
        );
    }

    #[test]
    fn stdin_defaults_to_plaintext_without_markdown_hint() {
        let doc = Document::from_stdin_text("# not a heading, just text".to_string(), false);
        assert_eq!(doc.content_type, ContentType::PlainText);
    }

    #[test]
    fn file_extension_dot_md_selects_markdown() {
        let dir = std::env::temp_dir().join(format!("nobotrs-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("sample.md");
        std::fs::write(&path, "# Title\n\nBody.").unwrap();
        let doc = Document::from_path(&path).unwrap();
        assert_eq!(doc.content_type, ContentType::Markdown);
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
