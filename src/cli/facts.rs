use super::{emit, load, Format};
use nobotrs::{config::Settings, deadline::Deadline};
use pulldown_cmark::{Event, Options, Parser, Tag, TagEnd};
use regex::Regex;
use serde::Serialize;
use std::{collections::BTreeMap, path::Path, sync::LazyLock, time::Duration};

// Narrow, complete value grammar. Unrecognized qualifications never become exact quantities.
static VALUE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
    r"(?ix)^(?P<approx>about\s+|approximately\s+|~)?(?P<unit>[$£€])?\s*(?P<num>-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)(?:\s*(?P<scale>million|billion|thousand|[kmb]))?\s*(?P<pct>%|percent)?$"
).unwrap()
});
// Bind only an explicit subject and attribute to a value. Keep fiscal periods and
// scenario words in the label so that different periods or estimates cannot collide.
static ASSERTION: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
    r"(?i)^(?P<label>[\p{L}\d][\p{L}\d '&’()/–-]{1,160}?)\s+(?:is|was|equals|totals|totaled|totalled)\s+(?P<value>.+)$"
).unwrap()
});
static DATE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$").unwrap());

static PERIOD: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)\bFY\s*[0-9]{2}(?:[0-9]{2})?\b").unwrap());

#[derive(Serialize)]
struct ClaimContext<'a> {
    entity: Option<&'a str>,
    attribute: Option<&'a str>,
    period: Option<&'a str>,
    unit: &'a str,
    qualifier: &'static str,
}

fn context<'a>(label: &'a str, unit: &'a str) -> ClaimContext<'a> {
    let period = PERIOD.find(label);
    let populated = |value: &'a str| (!value.trim().is_empty()).then(|| value.trim());
    ClaimContext {
        entity: period.and_then(|m| populated(&label[..m.start()])),
        attribute: match period {
            Some(m) => populated(&label[m.end()..]),
            None => populated(label),
        },
        period: period.map(|m| m.as_str()),
        unit: unit.strip_prefix("approximate ").unwrap_or(unit),
        qualifier: if unit.starts_with("approximate ") {
            "approximate"
        } else {
            "unqualified"
        },
    }
}

fn unbound_subject(label: &str) -> bool {
    matches!(
        label.split_whitespace().next(),
        Some("it" | "they" | "this" | "that" | "these" | "those" | "he" | "she" | "we")
    )
}

pub(super) fn canonical(value: &str) -> Option<(String, String)> {
    if DATE.is_match(value) {
        let year: u32 = value[..4].parse().ok()?;
        let month: u32 = value[5..7].parse().ok()?;
        let day: u32 = value[8..].parse().ok()?;
        let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
        let days = match month {
            2 if leap => 29,
            2 => 28,
            4 | 6 | 9 | 11 => 30,
            1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
            _ => return None,
        };
        return (day > 0 && day <= days).then(|| ("date".into(), value.into()));
    }
    let m = VALUE.captures(value)?;
    let unit = match (m.name("unit"), m.name("pct")) {
        (Some(_), Some(_)) => return None,
        (Some(u), None) => u.as_str(),
        (None, Some(_)) => "%",
        _ => "count",
    };
    let scale = match m
        .name("scale")
        .map(|x| x.as_str().to_ascii_lowercase())
        .as_deref()
    {
        Some("k" | "thousand") => 3,
        Some("m" | "million") => 6,
        Some("b" | "billion") => 9,
        _ => 0,
    };
    let clean = m["num"].replace(',', "");
    let (integer, decimal) = clean
        .trim_start_matches('-')
        .split_once('.')
        .unwrap_or((clean.trim_start_matches('-'), ""));
    let digits = format!("{integer}{decimal}");
    let significant = digits.trim_start_matches('0').trim_end_matches('0');
    let number = if significant.is_empty() {
        "0".to_string()
    } else {
        let zeros = digits.len() - digits.trim_end_matches('0').len();
        format!(
            "{}{significant}e{}",
            if clean.starts_with('-') { "-" } else { "" },
            scale + zeros as i64 - decimal.len() as i64
        )
    };
    Some((
        format!(
            "{}{}",
            if m.name("approx").is_some() {
                "approximate "
            } else {
                ""
            },
            unit
        ),
        number,
    ))
}

#[derive(Serialize)]
struct Mention {
    path: String,
    line: usize,
    column: usize,
    byte_offset: usize,
    label: String,
    unit: String,
    value: String,
    normalized: String,
    reference: bool,
}

struct Extractor<'a> {
    path: &'a str,
    raw: &'a str,
    lines: Vec<usize>,
    reference: bool,
    mentions: &'a mut Vec<Mention>,
    limit: usize,
    deadline: Deadline,
}
impl Extractor<'_> {
    fn add(&mut self, label: &str, value: &str, offset: usize) -> Result<(), String> {
        let value = value.trim().trim_end_matches('.');
        let Some((unit, normalized)) = canonical(value) else {
            return Ok(());
        };
        if label.trim().is_empty() {
            return Ok(());
        }
        if self.mentions.len() >= self.limit {
            return Err("fact candidate limit exceeded".into());
        }
        let line = self.lines.partition_point(|&start| start <= offset);
        self.mentions.push(Mention {
            path: self.path.into(),
            line,
            column: self.raw[self.lines[line - 1]..offset].chars().count() + 1,
            byte_offset: offset,
            label: label.trim().into(),
            unit,
            value: value.into(),
            normalized,
            reference: self.reference,
        });
        Ok(())
    }
    fn extract(&mut self, markdown: bool) -> Result<(), String> {
        let mut headers = Vec::new();
        let mut row = Vec::<(String, usize)>::new();
        let mut cell = None::<(String, usize)>;
        let mut table = false;
        let mut code = false;
        let mut quote_depth = 0usize;
        if markdown {
            for (event, span) in
                Parser::new_ext(self.raw, Options::ENABLE_TABLES).into_offset_iter()
            {
                if self.deadline.expired() {
                    return Err("fact analysis timed out".into());
                }
                match event {
                    Event::Start(Tag::Table(_)) => {
                        table = true;
                        headers.clear()
                    }
                    Event::End(TagEnd::Table) => table = false,
                    Event::Start(Tag::TableCell) => cell = Some((String::new(), span.start)),
                    Event::Text(t) if cell.is_some() => {
                        let (value, offset) = cell.as_mut().unwrap();
                        if value.is_empty() {
                            *offset = span.start
                        }
                        value.push_str(&t)
                    }
                    Event::End(TagEnd::TableCell) => {
                        if let Some(c) = cell.take() {
                            row.push(c)
                        }
                    }
                    Event::End(TagEnd::TableHead) => headers = row.drain(..).map(|x| x.0).collect(),
                    Event::End(TagEnd::TableRow) => {
                        if quote_depth == 0
                            && row.len() == headers.len()
                            && !row.is_empty()
                            && !row[0].0.trim().is_empty()
                        {
                            for ((value, offset), header) in row.iter().zip(&headers).skip(1) {
                                self.add(&format!("{} {}", row[0].0, header), value, *offset)?;
                            }
                        }
                        row.clear()
                    }
                    Event::Start(Tag::CodeBlock(_)) => code = true,
                    Event::End(TagEnd::CodeBlock) => code = false,
                    Event::Start(Tag::BlockQuote(_)) => quote_depth += 1,
                    Event::End(TagEnd::BlockQuote(_)) => quote_depth -= 1,
                    Event::Text(_) if !code && quote_depth == 0 && !table => {
                        self.field(&self.raw[span.clone()], span.start)?
                    }
                    _ => {}
                }
            }
        } else {
            for (index, line) in self.raw.lines().enumerate() {
                if self.deadline.expired() {
                    return Err("fact analysis timed out".into());
                }
                self.field(line, self.lines[index])?;
            }
        }
        Ok(())
    }
    fn field(&mut self, text: &str, start: usize) -> Result<(), String> {
        let mut begin = 0;
        for (offset, _) in text.match_indices('.') {
            if text[offset + 1..].starts_with(char::is_whitespace) {
                self.assertion(&text[begin..=offset], start + begin)?;
                begin = offset + 1;
            }
        }
        self.assertion(&text[begin..], start + begin)
    }
    fn assertion(&mut self, text: &str, start: usize) -> Result<(), String> {
        if let Some((label, value)) = text.split_once(':') {
            self.add(
                label,
                value,
                start + label.len() + 1 + value.len() - value.trim_start().len(),
            )?;
        } else if let Some(m) = ASSERTION.captures(text.trim()) {
            let value = m.name("value").expect("required capture");
            self.add(
                &m["label"],
                value.as_str(),
                start + text.len() - text.trim_start().len() + value.start(),
            )?;
        }
        Ok(())
    }
}

fn source_paths(
    inputs: &[String],
    deadline: Deadline,
    limit: usize,
) -> Result<Vec<String>, String> {
    let mut paths = Vec::new();
    for input in inputs {
        let root = Path::new(input);
        if input != "-"
            && root
                .symlink_metadata()
                .map_err(|e| format!("{input}: {e}"))?
                .is_symlink()
        {
            return Err(format!("source root is a symlink: {input}"));
        }
        if !root.is_dir() {
            paths.push(input.clone());
            continue;
        }
        for result in walkdir::WalkDir::new(root)
            .sort_by_file_name()
            .into_iter()
            .filter_entry(|e| {
                e.depth() == 0
                    || !e.file_type().is_dir()
                    || !matches!(
                        e.file_name().to_str(),
                        Some(".git" | "target" | "node_modules" | "vendor" | ".venv" | "venv")
                    )
            })
        {
            let entry = result.map_err(|e| e.to_string())?;
            if deadline.expired() {
                return Err("fact source traversal timed out".into());
            }
            if entry.file_type().is_file()
                && entry
                    .path()
                    .extension()
                    .and_then(|s| s.to_str())
                    .is_some_and(|e| {
                        matches!(e.to_ascii_lowercase().as_str(), "txt" | "md" | "markdown")
                    })
            {
                paths.push(
                    entry
                        .path()
                        .to_str()
                        .ok_or("source path is not UTF-8")?
                        .to_owned(),
                );
                if paths.len() > limit {
                    return Err("fact source count exceeds limit".into());
                }
            }
        }
    }
    Ok(paths)
}

pub(super) struct AnchoredValue {
    pub text: String,
    pub normalized: String,
    pub range: std::ops::Range<usize>,
}
pub(super) fn anchored_values(
    doc: &nobotrs::document::Document,
    limit: usize,
    deadline: Deadline,
) -> Result<Vec<AnchoredValue>, String> {
    let mut mentions = Vec::new();
    let lines = std::iter::once(0)
        .chain(doc.raw.match_indices('\n').map(|(i, _)| i + 1))
        .collect();
    Extractor {
        path: "",
        raw: &doc.raw,
        lines,
        reference: false,
        mentions: &mut mentions,
        limit,
        deadline,
    }
    .extract(matches!(
        doc.content_type,
        nobotrs::document::ContentType::Markdown
    ))?;
    Ok(mentions
        .into_iter()
        .map(|m| {
            let key = format!(
                "{} {} {}",
                m.label
                    .split_whitespace()
                    .collect::<Vec<_>>()
                    .join(" ")
                    .to_lowercase(),
                m.unit,
                m.normalized
            );
            AnchoredValue {
                text: format!("{}: {}", m.label, m.value),
                normalized: key,
                range: m.byte_offset..m.byte_offset + m.value.len(),
            }
        })
        .collect())
}

pub(super) fn check(
    paths: &[String],
    reference: Option<&str>,
    format: Format,
    settings: &Settings,
    markdown: bool,
) -> Result<i32, String> {
    if matches!(format, Format::Sarif) {
        return Err("facts check supports human or json output".into());
    }
    let mut mentions = vec![];
    let deadline = Deadline::new(Duration::from_millis(settings.timeout_ms));
    let paths = source_paths(paths, deadline, settings.max_candidates)?;
    let mut seen = std::collections::BTreeSet::new();
    for (path, is_reference) in reference
        .into_iter()
        .map(|p| (p, true))
        .chain(paths.iter().map(|p| (p.as_str(), false)))
    {
        let identity = if path == "-" {
            std::path::PathBuf::from("-")
        } else {
            std::fs::canonicalize(path).map_err(|e| format!("{path}: {e}"))?
        };
        if !seen.insert(identity) {
            return Err(format!("duplicate input: {path}"));
        }
        let input = load(path, settings.max_bytes)?;
        if input.truncated {
            return Err(format!("{path}: exceeds maximum input bytes"));
        }
        let lines = std::iter::once(0)
            .chain(input.text.match_indices('\n').map(|(i, _)| i + 1))
            .collect();
        Extractor {
            path,
            raw: &input.text,
            lines,
            reference: is_reference,
            mentions: &mut mentions,
            limit: settings.max_candidates,
            deadline,
        }
        .extract(markdown || nobotrs::document::Document::is_markdown(Path::new(path)))?;
    }
    let mut groups = BTreeMap::<(String, &str), Vec<&Mention>>::new();
    for m in &mentions {
        let label = m
            .label
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
            .to_lowercase();
        groups.entry((label, &m.unit)).or_default().push(m);
    }
    // Keep a short name and its possible expansions separate until an editor resolves them.
    let mut expansions = BTreeMap::new();
    for (label, unit) in groups.keys() {
        let c = context(label, unit);
        if let (Some(entity), Some(period), Some(attribute)) = (c.entity, c.period, c.attribute) {
            let mut words = entity.split_whitespace();
            if let (Some(first), Some(_)) = (words.next(), words.next()) {
                let initials: String = entity
                    .split_whitespace()
                    .filter_map(|w| w.chars().next())
                    .collect();
                for name in [first.to_owned(), initials] {
                    expansions
                        .entry((
                            name,
                            period.to_owned(),
                            attribute.to_owned(),
                            (*unit).to_owned(),
                        ))
                        .or_insert_with(std::collections::BTreeSet::new)
                        .insert(entity.to_owned());
                }
            }
        }
    }
    let mut findings = vec![];
    let mut code = 3;
    for ((label, unit), entries) in groups {
        if deadline.expired() {
            return Err("fact comparison timed out".into());
        }
        let c = context(&label, unit);
        let aliases =
            c.entity
                .zip(c.period)
                .zip(c.attribute)
                .and_then(|((entity, period), attribute)| {
                    expansions.get(&(
                        entity.to_owned(),
                        period.to_owned(),
                        attribute.to_owned(),
                        unit.to_owned(),
                    ))
                });
        let status = if unbound_subject(&label) || aliases.is_some() {
            "ambiguous"
        } else if entries
            .iter()
            .any(|e| e.normalized != entries[0].normalized)
        {
            "conflict"
        } else if entries.iter().all(|e| e.reference) {
            "missing_expected"
        } else if entries.len() < 2 {
            "unresolved"
        } else {
            "compatible"
        };
        match status {
            "conflict" | "missing_expected" => code = 1,
            "compatible" if code == 3 => code = 0,
            _ => {}
        }
        if matches!(format, Format::Human) {
            emit(&format!("{status}: {label} ({unit})"))?;
            if let Some(names) = aliases {
                emit(&format!(
                    "  Confirm the entity against these possible source names: {}",
                    names.iter().cloned().collect::<Vec<_>>().join(", ")
                ))?;
            }
            for e in &entries {
                emit(&format!(
                    "  {}:{}:{}  {}",
                    e.path, e.line, e.column, e.value
                ))?;
            }
        }
        findings.push(
            serde_json::json!({"status":status,"label":label,"unit":unit,"context":c,"possible_entity_expansions":aliases,"mentions":entries}),
        );
    }
    if matches!(format, Format::Json) {
        emit(&serde_json::json!({"schema_version":"1.0.0","facts_extracted":mentions.len(),"complete":true,"groups":findings,"exit_code":code}).to_string())?;
    } else if findings.is_empty() {
        emit("No checkable labelled quantities or dates found.")?
    }
    Ok(code)
}
