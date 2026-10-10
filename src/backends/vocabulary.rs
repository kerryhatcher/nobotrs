use crate::{
    availability::Availability,
    backend::{DetectorBackend, ScoreOutcome, SignalFamily},
    deadline::Deadline,
    dictionary::{Dictionary, MatchType},
    document::Document,
    error::Error,
    score::{ConfidenceTier, Score, VoteStrength},
};
use aho_corasick::{AhoCorasick, AhoCorasickBuilder, MatchKind};
use regex::{Regex, RegexBuilder};
use std::collections::BTreeMap;
const REGEX_SIZE_LIMIT: usize = 1 << 16;
#[derive(Clone)]
struct Entry {
    id: String,
    suggestion: Option<String>,
    whole_word: bool,
}
struct ExactPath {
    automaton: AhoCorasick,
    entries: Vec<Entry>,
}
struct RegexEntry {
    entry: Entry,
    regex: Regex,
}
pub struct Vocabulary {
    exact: Vec<ExactPath>,
    regex: Vec<RegexEntry>,
}
impl Vocabulary {
    pub fn new(dictionary: Dictionary) -> Result<Self, String> {
        dictionary.validate()?;
        let mut exact = vec![];
        for sensitive in [false, true] {
            let mut entries = vec![];
            let mut patterns = vec![];
            for e in &dictionary.entries {
                if !matches!(e.match_type, MatchType::Exact) || e.case_sensitive != sensitive {
                    continue;
                }
                for pattern in std::iter::once(&e.pattern).chain(&e.variants) {
                    patterns.push(pattern.clone());
                    entries.push(Entry {
                        id: e.id.clone(),
                        suggestion: e.suggested_replacements.first().cloned(),
                        whole_word: e.whole_word,
                    });
                }
            }
            if !patterns.is_empty() {
                let automaton = AhoCorasickBuilder::new()
                    .match_kind(MatchKind::Standard)
                    .ascii_case_insensitive(!sensitive)
                    .build(patterns)
                    .map_err(|e| e.to_string())?;
                exact.push(ExactPath { automaton, entries });
            }
        }
        let mut regex = vec![];
        for e in &dictionary.entries {
            if matches!(e.match_type, MatchType::Regex) {
                let re = RegexBuilder::new(&e.pattern)
                    .case_insensitive(!e.case_sensitive)
                    .size_limit(REGEX_SIZE_LIMIT)
                    .build()
                    .map_err(|err| format!("entry '{}': {err}", e.id))?;
                if re.is_match("") {
                    return Err(format!("entry '{}' matches empty input", e.id));
                }
                regex.push(RegexEntry {
                    entry: Entry {
                        id: e.id.clone(),
                        suggestion: e.suggested_replacements.first().cloned(),
                        whole_word: e.whole_word,
                    },
                    regex: re,
                });
            }
        }
        Ok(Self { exact, regex })
    }
    pub fn score_limited(&self, doc: &Document, deadline: Deadline, cap: usize) -> ScoreOutcome {
        let mut candidates = vec![];
        let mut examined = 0usize;
        let mut candidate_bytes = 0usize;
        let mut failure = None;
        let mut covered = 0;
        'blocks: for span in &doc.prose_spans {
            let text = &doc.prose[span.clone()];
            for path in &self.exact {
                for m in path.automaton.find_overlapping_iter(text) {
                    if deadline.expired() {
                        failure = Some(Error::Timeout);
                        break 'blocks;
                    }
                    examined += 1;
                    if examined > cap {
                        failure = Some(Error::ResourceLimit("vocabulary candidate budget".into()));
                        break 'blocks;
                    }
                    let entry = &path.entries[m.pattern().as_usize()];
                    if !entry.whole_word || is_word_bounded(text, m.start(), m.end()) {
                        candidate_bytes += m.end() - m.start();
                        if candidate_bytes > 8_388_608 {
                            failure =
                                Some(Error::ResourceLimit("candidate text byte budget".into()));
                            break 'blocks;
                        }
                        candidates.push(doc.finding(
                            span.start + m.start()..span.start + m.end(),
                            &entry.id,
                            entry.suggestion.clone(),
                        ));
                    }
                }
            }
            for re in &self.regex {
                let mut pos = 0;
                while pos < text.len() {
                    if deadline.expired() {
                        failure = Some(Error::Timeout);
                        break 'blocks;
                    }
                    let Some(m) = re.regex.find_at(text, pos) else {
                        break;
                    };
                    examined += 1;
                    if examined > cap {
                        failure = Some(Error::ResourceLimit("vocabulary candidate budget".into()));
                        break 'blocks;
                    }
                    if m.start() != m.end()
                        && (!re.entry.whole_word || is_word_bounded(text, m.start(), m.end()))
                    {
                        candidate_bytes += m.end() - m.start();
                        if candidate_bytes > 8_388_608 {
                            failure =
                                Some(Error::ResourceLimit("candidate text byte budget".into()));
                            break 'blocks;
                        }
                        candidates.push(doc.finding(
                            span.start + m.start()..span.start + m.end(),
                            &re.entry.id,
                            re.entry.suggestion.clone(),
                        ));
                    }
                    // Within-rule overlaps enumerate every possible starting position. Regex alternation
                    // retains Rust regex's leftmost-first choice at a given start (not all alternatives).
                    pos = m.start() + text[m.start()..].chars().next().map_or(1, char::len_utf8);
                }
            }
            covered = span.end;
        }
        if deadline.expired() {
            failure.get_or_insert(Error::Timeout);
        }
        candidates.sort_by(|a, b| {
            (a.prose_offset.start, a.prose_offset.end, &a.rule_id).cmp(&(
                b.prose_offset.start,
                b.prose_offset.end,
                &b.rule_id,
            ))
        });
        candidates.dedup_by(|a, b| a.rule_id == b.rule_id && a.prose_offset == b.prose_offset);
        let mut score = Score::new(
            "vocabulary".into(),
            SignalFamily::Vocabulary,
            ConfidenceTier::Medium,
            VoteStrength::None,
            vec![],
        );
        score.candidates = candidates;
        select_effective(&mut score);
        if let Some(reason) = failure {
            score.voting_eligible = false;
            ScoreOutcome::Incomplete {
                score,
                reason,
                coverage: covered as f64 / doc.prose.len().max(1) as f64,
            }
        } else {
            ScoreOutcome::Scored(score)
        }
    }
}
fn is_word_bounded(text: &str, start: usize, end: usize) -> bool {
    let word = |c: char| c.is_alphanumeric() || c == '_';
    !text[..start].chars().next_back().is_some_and(word)
        && !text[end..].chars().next().is_some_and(word)
}
/// Suppression must already have been applied to candidates. O(n log n) interval selection.
pub fn select_effective(score: &mut Score) {
    let mut order: Vec<_> = (0..score.candidates.len())
        .filter(|&i| score.candidates[i].suppression.is_none())
        .collect();
    order.sort_by(|&a, &b| {
        let a = &score.candidates[a];
        let b = &score.candidates[b];
        (
            std::cmp::Reverse(a.prose_offset.len()),
            a.prose_offset.start,
            &a.rule_id,
        )
            .cmp(&(
                std::cmp::Reverse(b.prose_offset.len()),
                b.prose_offset.start,
                &b.rule_id,
            ))
    });
    let mut kept: BTreeMap<usize, usize> = BTreeMap::new();
    for c in &mut score.candidates {
        c.disposition = if c.suppression.is_some() {
            "suppressed"
        } else {
            "overlap_excluded"
        }
        .into();
    }
    for i in order {
        let c = &mut score.candidates[i];
        let r = &c.prose_offset;
        let prev = kept
            .range(..=r.start)
            .next_back()
            .is_some_and(|(_, end)| *end > r.start);
        let next = kept
            .range(r.start..)
            .next()
            .is_some_and(|(start, _)| *start < r.end);
        if !prev && !next {
            kept.insert(r.start, r.end);
            c.disposition = "selected".into();
        }
    }
    score.evidence = score
        .candidates
        .iter()
        .filter(|c| c.disposition == "selected")
        .cloned()
        .collect();
    score.evidence.sort_by_key(|c| c.prose_offset.start);
    score.vote = match score.evidence.len() {
        4.. => VoteStrength::Strong,
        2.. => VoteStrength::Suspicious,
        _ => VoteStrength::None,
    };
    score.metrics.insert(
        "effective_occurrences".into(),
        crate::score::Metric {
            value: score.evidence.len() as f64,
            unit: "occurrences".into(),
            method: "suppression-before-longest-selection-v1".into(),
        },
    );
}
impl DetectorBackend for Vocabulary {
    fn name(&self) -> &str {
        "vocabulary"
    }
    fn family(&self) -> SignalFamily {
        SignalFamily::Vocabulary
    }
    fn availability(&self) -> Availability {
        Availability::Ready
    }
    fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome {
        self.score_limited(doc, deadline, 10_000)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend::SignalFamily;
    use crate::deadline::Deadline;
    use crate::dictionary::{Dictionary, DictionaryEntry, EntryKind, MatchType};
    use crate::document::Document;
    use crate::score::VoteStrength;

    fn backend() -> Vocabulary {
        Vocabulary::new(Dictionary::embedded()).expect("embedded dictionary must compile")
    }

    /// Minimal hand-built entries for the crossing-overlap test below —
    /// every field the schema requires, with the parts irrelevant to that
    /// test (variants, suggestions, model_era, source, notes) left empty.
    fn exact_entry(id: &str, pattern: &str) -> DictionaryEntry {
        DictionaryEntry {
            id: id.to_string(),
            kind: EntryKind::Word,
            match_type: MatchType::Exact,
            pattern: pattern.to_string(),
            variants: vec![],
            case_sensitive: false,
            whole_word: false,
            family: SignalFamily::Vocabulary,
            category: "test".to_string(),
            suggested_replacements: vec![],
            model_era: vec![],
            source: None,
            notes: None,
        }
    }

    fn regex_entry(id: &str, pattern: &str) -> DictionaryEntry {
        DictionaryEntry {
            id: id.to_string(),
            kind: EntryKind::Phrase,
            match_type: MatchType::Regex,
            pattern: pattern.to_string(),
            variants: vec![],
            case_sensitive: false,
            whole_word: false,
            family: SignalFamily::Vocabulary,
            category: "test".to_string(),
            suggested_replacements: vec![],
            model_era: vec![],
            source: None,
            notes: None,
        }
    }

    fn score_text(text: &str) -> crate::score::Score {
        let backend = backend();
        let doc = Document::from_stdin_text(text.to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        match backend.score(&doc, deadline) {
            crate::backend::ScoreOutcome::Scored(score) => score,
            _other => panic!("expected Scored, got a different outcome"),
        }
    }

    #[test]
    fn zero_hits_votes_none() {
        let score = score_text("The cat sat quietly on the warm windowsill all afternoon.");
        assert_eq!(score.vote, VoteStrength::None);
    }

    #[test]
    fn two_hits_votes_suspicious() {
        let score = score_text("Let's delve into this and leverage what we learn.");
        assert_eq!(score.vote, VoteStrength::Suspicious);
    }

    #[test]
    fn four_hits_votes_strong() {
        let score = score_text(
            "Let's delve into this multifaceted, nuanced topic and leverage what we learn.",
        );
        assert_eq!(score.vote, VoteStrength::Strong);
    }

    #[test]
    fn whole_word_does_not_match_inside_longer_word() {
        // "harness" must not match inside "harnessed" (the word-boundary
        // check must reject the substring match since it's not the whole
        // token). No other dictionary entry is a substring of "operation",
        // so the sentence should produce zero hits overall.
        let score = score_text("The operation was harnessed successfully by the team.");
        assert_eq!(score.vote, VoteStrength::None);
    }

    #[test]
    fn case_insensitive_matches_sentence_initial_capitalized_form() {
        let score = score_text("Delve into this and also delve into that thoroughly today.");
        assert_eq!(score.vote, VoteStrength::Suspicious);
    }

    #[test]
    fn phrase_regex_entry_matches() {
        let score = score_text("It's not just a fix, it's a whole new approach worth trying.");
        assert!(!score.evidence.is_empty());
    }

    #[test]
    fn longest_match_wins_suppresses_full_containment_overlap() {
        // The dictionary has both an exact word entry "embark" (id: embark)
        // and a regex phrase entry "embark on a journey" (id:
        // embark-on-a-journey). Against this sentence, aho-corasick finds a
        // 6-byte exact hit for "embark" fully contained inside the regex's
        // longer phrase hit — a genuine overlap, not a hypothetical one.
        // Longest-match-wins (spec Sec 11.3) must suppress the shorter,
        // contained "embark" hit so no two evidence entries overlap.
        let score =
            score_text("The team decided to embark on a journey toward better documentation.");
        assert!(
            !score.evidence.is_empty(),
            "expected at least one evidence entry from the overlapping matches"
        );
        for (i, a) in score.evidence.iter().enumerate() {
            for b in score.evidence.iter().skip(i + 1) {
                let overlaps =
                    a.raw_offset.start < b.raw_offset.end && b.raw_offset.start < a.raw_offset.end;
                assert!(
                    !overlaps,
                    "evidence spans {:?} and {:?} overlap",
                    a.raw_offset, b.raw_offset
                );
            }
        }
    }

    #[test]
    fn longest_match_wins_suppresses_crossing_overlap() {
        // Unequal/crossing exact and regex alternatives are retained until selection.
        let dictionary = Dictionary {
            schema_version: "1.0.0".to_string(),
            dictionary_version: "test".to_string(),
            entries: vec![
                regex_entry("crossing-regex", "abcde"),
                exact_entry("crossing-exact", "defgh"),
            ],
        };
        let backend = Vocabulary::new(dictionary)
            .expect("synthetic crossing-overlap dictionary must compile");
        let doc = Document::from_stdin_text("abcdefgh".to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        let score = match backend.score(&doc, deadline) {
            crate::backend::ScoreOutcome::Scored(score) => score,
            _other => panic!("expected Scored, got a different outcome"),
        };

        // Only one of the two crossing hits may survive the merge.
        assert_eq!(
            score.evidence.len(),
            1,
            "crossing overlap must collapse to exactly one kept hit, got {:?}",
            score.evidence
        );
        for (i, a) in score.evidence.iter().enumerate() {
            for b in score.evidence.iter().skip(i + 1) {
                let overlaps =
                    a.raw_offset.start < b.raw_offset.end && b.raw_offset.start < a.raw_offset.end;
                assert!(
                    !overlaps,
                    "evidence spans {:?} and {:?} overlap",
                    a.raw_offset, b.raw_offset
                );
            }
        }
    }
}
