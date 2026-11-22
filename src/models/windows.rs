//! Opt-in section packing. Body token IDs come from one untruncated encoding.
use crate::{deadline::Deadline, error::Error};
use std::ops::Range;
use tokenizers::{Encoding, Tokenizer};
pub const PACKING_POLICY: &str = "section-packed-v1";
pub const AGGREGATION_POLICY: &str = "token-weighted-mean-v1";
pub const MIN_HOTSPOT_TOKENS: usize = 128;
#[derive(Debug, Clone)]
pub struct PlanUnit {
    pub text: Range<usize>,
    pub paragraph: usize,
    pub heading: Option<String>,
}
#[derive(Debug, Clone)]
pub struct Window {
    pub index: usize,
    pub text: Range<usize>,
    pub units: Range<usize>,
    pub paragraphs: Range<usize>,
    pub heading: Option<String>,
    pub body_tokens: usize,
    pub ids: Vec<u32>,
    pub split: bool,
}
fn token_error(e: impl std::fmt::Display) -> Error {
    Error::InternalError(format!("window tokenizer: {e}"))
}
pub fn plan_windows(
    tokenizer: &Tokenizer,
    text: &str,
    units: &[PlanUnit],
    max_tokens: usize,
) -> Result<Vec<Window>, Error> {
    let mut tok = tokenizer.clone();
    tok.with_truncation(None).map_err(token_error)?;
    tok.with_padding(None);
    let specials = tok.encode("", true).map_err(token_error)?.len();
    let budget = max_tokens
        .checked_sub(specials)
        .filter(|&b| b > 0)
        .ok_or_else(|| Error::ConfigError("token budget leaves no body capacity".into()))?;
    let full = tok.encode(text, false).map_err(token_error)?;
    if full.is_empty() {
        return Ok(vec![]);
    }
    if units.is_empty()
        || units.windows(2).any(|w| w[0].text.end > w[1].text.start)
        || units.iter().any(|u| {
            u.text.end > text.len()
                || !text.is_char_boundary(u.text.start)
                || !text.is_char_boundary(u.text.end)
        })
    {
        return Err(Error::InternalError(
            "invalid or missing window units".into(),
        ));
    }
    let offsets = full.get_offsets();
    let owners: Vec<_> = offsets
        .iter()
        .map(|&(start, _)| {
            units
                .partition_point(|u| u.text.start <= start)
                .saturating_sub(1)
        })
        .collect();
    let mut windows = Vec::new();
    let mut start = 0;
    while start < full.len() {
        let first = owners[start];
        let section_end = (start + 1..full.len())
            .find(|&i| units[owners[i]].heading != units[first].heading)
            .unwrap_or(full.len());
        let ceiling = (start + budget).min(section_end);
        let mut end = ceiling;
        if ceiling < section_end {
            if let Some(boundary) = (start + 1..=ceiling)
                .rev()
                .find(|&i| units[owners[i - 1]].paragraph != units[owners[i]].paragraph)
            {
                end = boundary;
            } else if let Some(boundary) = (start + 1..=ceiling)
                .rev()
                .find(|&i| owners[i - 1] != owners[i])
            {
                end = boundary;
            }
        }
        // Multiple byte-fallback tokens can share one UTF-8 scalar. Do not navigate into it.
        while end > start && end < full.len() && offsets[end].0 < offsets[end - 1].1 {
            end -= 1;
        }
        if end == start {
            return Err(Error::ResourceLimit(
                "token budget cannot contain an atomic UTF-8 character".into(),
            ));
        }
        let slice = start..end;
        let body = Encoding::new(
            full.get_ids()[slice.clone()].to_vec(),
            full.get_type_ids()[slice.clone()].to_vec(),
            full.get_tokens()[slice.clone()].to_vec(),
            full.get_word_ids()[slice.clone()].to_vec(),
            offsets[slice.clone()].to_vec(),
            vec![0; end - start],
            vec![1; end - start],
            vec![],
            Default::default(),
        );
        let wrapped = tok.post_process(body, None, true).map_err(token_error)?;
        if wrapped.len() > max_tokens {
            return Err(Error::InternalError(
                "postprocessor exceeded window token limit".into(),
            ));
        }
        let last = owners[end - 1];
        let left = if start == 0 { 0 } else { offsets[start].0 };
        let right = if end == full.len() {
            text.len()
        } else {
            offsets[end].0
        };
        if !text.is_char_boundary(left) || !text.is_char_boundary(right) {
            return Err(Error::InternalError("non-UTF8 tokenizer offsets".into()));
        }
        windows.push(Window {
            index: windows.len(),
            text: left..right,
            units: first..last + 1,
            paragraphs: units[first].paragraph..units[last].paragraph + 1,
            heading: units[first].heading.clone(),
            body_tokens: end - start,
            ids: wrapped.get_ids().to_vec(),
            split: (start > 0 && owners[start - 1] == first)
                || (end < full.len() && owners[end] == last),
        });
        start = end;
    }
    Ok(windows)
}
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WindowStatus {
    Scored,
    TimedOut,
    NotRun,
    Failed(String),
}
#[derive(Debug, Clone)]
pub struct WindowResult {
    pub index: usize,
    pub status: WindowStatus,
    pub raw_output: Option<f64>,
}
#[derive(Debug, Clone)]
pub struct WindowRun {
    pub results: Vec<WindowResult>,
    pub covered_tokens: usize,
    pub eligible_tokens: usize,
    pub aggregate: Option<f64>,
}
pub fn run_windows(
    windows: &[Window],
    deadline: Deadline,
    mut infer: impl FnMut(&[u32]) -> Result<f64, Error>,
) -> WindowRun {
    let mut results = Vec::new();
    let mut covered_tokens = 0;
    let mut weighted = 0.0;
    let mut stopped = false;
    for w in windows {
        let (status, raw_output) = if stopped {
            (WindowStatus::NotRun, None)
        } else if deadline.expired() {
            stopped = true;
            (WindowStatus::TimedOut, None)
        } else {
            match infer(&w.ids) {
                Ok(raw) if raw.is_finite() && !deadline.expired() => {
                    covered_tokens += w.body_tokens;
                    weighted += raw * w.body_tokens as f64;
                    (WindowStatus::Scored, Some(raw))
                }
                Ok(_) if deadline.expired() => {
                    stopped = true;
                    (WindowStatus::TimedOut, None)
                }
                Ok(_) => (WindowStatus::Failed("non-finite output".into()), None),
                Err(Error::Timeout) => {
                    stopped = true;
                    (WindowStatus::TimedOut, None)
                }
                Err(e) => (WindowStatus::Failed(e.to_string()), None),
            }
        };
        results.push(WindowResult {
            index: w.index,
            status,
            raw_output,
        });
    }
    let eligible_tokens = windows.iter().map(|w| w.body_tokens).sum();
    let aggregate =
        if eligible_tokens > 0 && results.iter().all(|r| r.status == WindowStatus::Scored) {
            Some(weighted / eligible_tokens as f64)
        } else {
            None
        };
    WindowRun {
        results,
        covered_tokens,
        eligible_tokens,
        aggregate,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn tok() -> Tokenizer {
        let model = tokenizers::models::wordlevel::WordLevel::builder()
            .vocab(
                [
                    ("[UNK]".into(), 0),
                    ("one".into(), 1),
                    ("two".into(), 2),
                    ("three".into(), 3),
                    ("four".into(), 4),
                    ("five".into(), 5),
                ]
                .into_iter()
                .collect(),
            )
            .unk_token("[UNK]".into())
            .build()
            .unwrap();
        let mut t = Tokenizer::new(model);
        t.with_pre_tokenizer(Some(tokenizers::pre_tokenizers::whitespace::Whitespace));
        t
    }
    fn unit(text: &str) -> Vec<PlanUnit> {
        vec![PlanUnit {
            text: 0..text.len(),
            paragraph: 0,
            heading: None,
        }]
    }
    #[test]
    fn below_at_above_and_exact_token_coverage() {
        for (text, n) in [
            ("one two three", 1),
            ("one two three four", 1),
            ("one two three four five", 2),
        ] {
            let ws = plan_windows(&tok(), text, &unit(text), 4).unwrap();
            assert_eq!(ws.len(), n);
            assert_eq!(
                ws.iter().map(|w| w.body_tokens).sum::<usize>(),
                tok().encode(text, false).unwrap().len()
            );
            assert!(ws.iter().all(|w| w.ids.len() <= 4));
            assert!(ws.windows(2).all(|w| w[0].text.end == w[1].text.start));
        }
    }
    #[test]
    fn heading_and_unit_splits() {
        let text = "one two three four five";
        let units = vec![
            PlanUnit {
                text: 0..7,
                paragraph: 0,
                heading: Some("A".into()),
            },
            PlanUnit {
                text: 8..text.len(),
                paragraph: 1,
                heading: Some("B".into()),
            },
        ];
        let ws = plan_windows(&tok(), text, &units, 10).unwrap();
        assert_eq!(ws.len(), 2);
        assert_eq!(ws[0].heading.as_deref(), Some("A"));
        assert_eq!(ws[1].heading.as_deref(), Some("B"));
        let text = ["one"; 11].join(" ");
        let ws = plan_windows(&tok(), &text, &unit(&text), 4).unwrap();
        assert_eq!(ws.len(), 3);
        assert!(ws.iter().all(|w| w.split));
        assert_eq!(ws.iter().map(|w| w.body_tokens).sum::<usize>(), 11);
    }
    #[test]
    fn deadline_failure_and_weighted_mean() {
        let text = "one two three four five";
        let ws = plan_windows(&tok(), text, &unit(text), 4).unwrap();
        let mut n = 0;
        let run = run_windows(
            &ws,
            Deadline::new(std::time::Duration::from_secs(1)),
            |_| {
                n += 1;
                Ok(n as f64)
            },
        );
        assert_eq!(run.aggregate, Some(1.2));
        let mut n = 0;
        let run = run_windows(
            &ws,
            Deadline::new(std::time::Duration::from_secs(1)),
            |_| {
                n += 1;
                if n == 2 {
                    Err(Error::Timeout)
                } else {
                    Ok(1.0)
                }
            },
        );
        assert_eq!(run.covered_tokens, 4);
        assert!(run.aggregate.is_none());
        assert_eq!(run.results[1].status, WindowStatus::TimedOut);
        let run = run_windows(&ws, Deadline::new(std::time::Duration::ZERO), |_| {
            panic!("must not run")
        });
        assert_eq!(run.results[0].status, WindowStatus::TimedOut);
        assert_eq!(run.results[1].status, WindowStatus::NotRun);
    }
    #[test]
    fn tail_only_change_preserves_first_window() {
        let a = "one two three four one";
        let b = "one two three four two";
        let x = plan_windows(&tok(), a, &unit(a), 4).unwrap();
        let y = plan_windows(&tok(), b, &unit(b), 4).unwrap();
        assert_eq!(x[0].ids, y[0].ids);
        assert_ne!(x[1].ids, y[1].ids);
    }
    #[test]
    fn special_tokens_count_toward_budget_and_paragraphs_pack_whole() {
        let mut tokenizer = tok();
        tokenizer.with_post_processor(Some(tokenizers::processors::bert::BertProcessing::new(
            ("[SEP]".into(), 6),
            ("[CLS]".into(), 7),
        )));
        let text = "one two three four five";
        let units = vec![
            PlanUnit {
                text: 0..13,
                paragraph: 0,
                heading: None,
            },
            PlanUnit {
                text: 14..text.len(),
                paragraph: 1,
                heading: None,
            },
        ];
        let w = plan_windows(&tokenizer, text, &units, 6).unwrap();
        assert_eq!(w.len(), 2);
        assert_eq!(w[0].body_tokens, 3);
        assert_eq!(w[1].body_tokens, 2);
        assert!(w
            .iter()
            .all(|w| w.ids.len() == w.body_tokens + 2 && w.ids.len() <= 6));
        assert_eq!(w[0].paragraphs, 0..1);
        assert_eq!(w[1].paragraphs, 1..2);
    }
}
