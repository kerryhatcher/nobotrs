use nobotrs::document::{ContentType, Document};
use pulldown_cmark::{Event, Options, Parser, Tag, TagEnd};
use regex::Regex;
use serde::Serialize;
use std::{collections::BTreeMap, ops::Range, sync::LazyLock};

static NUMBERS: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?ix)(?:about\s+|approximately\s+|~)?(?:FY\s*)?[$€£]?[-−]?\d+(?:,\d{3})*(?:\.\d+)?(?:[–-]\d+(?:\.\d+)?)?(?:\s*(?:percent\b|%|million\b|billion\b|thousand\b|[kmb]\b))?").unwrap()
});
static QUOTES: LazyLock<Regex> = LazyLock::new(|| Regex::new(r#"“[^”\n]+”|"[^"\n]+""#).unwrap());
static URL: LazyLock<Regex> = LazyLock::new(|| Regex::new(r#"https?://[^\s<>"\)\]]+"#).unwrap());
static NAME: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\b\p{Lu}[\p{L}’-]+(?: +\p{Lu}[\p{L}’-]+)+\b").unwrap());
static QUALIFIER: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\b(may|might|must|will|cannot|not|never|no longer|at least|at most|projected|estimated)\b").unwrap()
});

#[derive(Debug, Clone, Serialize)]
pub(super) struct Invariant {
    pub kind: &'static str,
    pub text: String,
    pub normalized: String,
    pub source_ranges: Vec<Range<usize>>,
    pub line: u32,
    pub column: u32,
}
impl Invariant {
    pub fn hard(&self) -> bool {
        matches!(self.kind, "number" | "quote" | "url" | "code" | "link")
    }
}
fn url_value(s: &str) -> String {
    if let Some((scheme, rest)) = s.split_once("://") {
        let end = rest.find(['/', '?', '#']).unwrap_or(rest.len());
        let tail = &rest[end..];
        return format!(
            "{}://{}{}",
            scheme.to_ascii_lowercase(),
            rest[..end].to_ascii_lowercase(),
            if tail == "/" { "" } else { tail }
        );
    }
    s.to_owned()
}
pub(super) fn extract(
    doc: &Document,
    limit: usize,
    deadline: nobotrs::deadline::Deadline,
) -> Result<Vec<Invariant>, String> {
    let mut items = Vec::new();
    let mut add =
        |kind, text: &str, normalized: String, ranges: Vec<Range<usize>>| -> Result<(), String> {
            if items.len() >= limit {
                return Err("revision invariant limit exceeded".into());
            }
            if let Some(first) = ranges.first() {
                let (line, column) = doc.location(first.start);
                items.push(Invariant {
                    kind,
                    text: text.into(),
                    normalized,
                    source_ranges: ranges,
                    line,
                    column,
                });
            }
            Ok(())
        };
    for span in &doc.prose_spans {
        if deadline.expired() {
            return Err("revision scan timed out".into());
        }
        let text = &doc.prose[span.clone()];
        for (kind, regex) in [
            ("number", &*NUMBERS),
            ("quote", &*QUOTES),
            ("name", &*NAME),
            ("qualifier", &*QUALIFIER),
            ("url", &*URL),
        ] {
            for hit in regex.find_iter(text) {
                let original = hit.as_str();
                let value = match kind {
                    "number" => super::facts::canonical(original)
                        .map(|(u, v)| format!("{u} {v}"))
                        .unwrap_or_else(|| original.replace('–', "-")),
                    "quote" => original
                        .trim_matches(['"', '“', '”'])
                        .split_whitespace()
                        .collect::<Vec<_>>()
                        .join(" "),
                    "qualifier" => original.to_lowercase(),
                    "url" => url_value(original.trim_end_matches(['.', ',', ';'])),
                    _ => original.to_owned(),
                };
                add(
                    kind,
                    original,
                    value,
                    doc.source_ranges(span.start + hit.start()..span.start + hit.end()),
                )?;
            }
        }
    }
    if matches!(doc.content_type, ContentType::Markdown) {
        let mut block = None;
        for (event, span) in Parser::new_ext(&doc.raw, Options::ENABLE_TABLES).into_offset_iter() {
            match event {
                Event::Start(Tag::CodeBlock(_)) => block = Some((span.start, String::new())),
                Event::Text(text) if block.is_some() => block.as_mut().unwrap().1.push_str(&text),
                Event::End(TagEnd::CodeBlock) => {
                    if let Some((start, value)) = block.take() {
                        add(
                            "code",
                            &value,
                            value.clone(),
                            std::iter::once(start..span.end).collect(),
                        )?
                    }
                }
                Event::Code(text) => add(
                    "code",
                    &text,
                    text.to_string(),
                    std::iter::once(span).collect(),
                )?,
                Event::Start(Tag::Link { dest_url, .. } | Tag::Image { dest_url, .. }) => add(
                    "link",
                    &dest_url,
                    url_value(&dest_url),
                    std::iter::once(span).collect(),
                )?,
                _ => {}
            }
        }
    }
    for claim in super::facts::anchored_values(doc, limit, deadline)? {
        add(
            "anchored_claim",
            &claim.text,
            claim.normalized,
            std::iter::once(claim.range).collect(),
        )?;
    }
    items.sort_by_key(|i| i.source_ranges[0].start);
    Ok(items)
}
pub(super) fn difference(left: &[Invariant], right: &[Invariant]) -> Vec<Invariant> {
    let mut available = BTreeMap::new();
    for i in right {
        *available.entry((i.kind, &i.normalized)).or_insert(0usize) += 1;
    }
    left.iter()
        .filter(|i| {
            let count = available.entry((i.kind, &i.normalized)).or_default();
            if *count == 0 {
                true
            } else {
                *count -= 1;
                false
            }
        })
        .cloned()
        .collect()
}
