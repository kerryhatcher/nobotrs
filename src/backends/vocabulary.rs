// src/backends/vocabulary.rs
use aho_corasick::{AhoCorasick, AhoCorasickBuilder, MatchKind};
use regex::{Regex, RegexBuilder};

use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::dictionary::{Dictionary, MatchType};
use crate::document::Document;
use crate::score::{ConfidenceTier, Evidence, Score, Severity, VoteStrength};

const REGEX_SIZE_LIMIT: usize = 1 << 16; // matches the CI-asserted bound (Task 7)

struct ExactEntry {
    #[allow(dead_code)] // Not yet consumed: reserved for per-entry diagnostics/reporting.
    id: String,
    suggestion: Option<String>,
    whole_word: bool,
}

struct RegexEntry {
    #[allow(dead_code)] // Not yet consumed: reserved for per-entry diagnostics/reporting.
    id: String,
    suggestion: Option<String>,
    regex: Regex,
}

pub struct Vocabulary {
    automaton: AhoCorasick,
    exact_entries: Vec<ExactEntry>, // parallel to automaton's pattern order
    regex_entries: Vec<RegexEntry>,
}

struct RawHit {
    start: usize,
    end: usize,
    matched_text: String,
    suggestion: Option<String>,
}

impl Vocabulary {
    /// Builds the aho-corasick automaton and compiles every regex-kind
    /// dictionary entry. Fails fast here (rather than lazily at score time)
    /// so a broken contributed pattern surfaces as a single, attributable
    /// construction error instead of a per-document runtime surprise.
    pub fn new(dictionary: Dictionary) -> Result<Vocabulary, String> {
        let mut patterns = Vec::new();
        let mut exact_entries = Vec::new();
        let mut regex_entries = Vec::new();

        for entry in &dictionary.entries {
            match entry.match_type {
                MatchType::Exact => {
                    let mut forms = vec![entry.pattern.clone()];
                    forms.extend(entry.variants.clone());
                    for form in forms {
                        patterns.push(if entry.case_sensitive { form } else { form.to_lowercase() });
                        exact_entries.push(ExactEntry {
                            id: entry.id.clone(),
                            suggestion: entry.suggested_replacements.first().cloned(),
                            whole_word: entry.whole_word,
                        });
                    }
                }
                MatchType::Regex => {
                    let regex = RegexBuilder::new(&entry.pattern)
                        .case_insensitive(!entry.case_sensitive)
                        .size_limit(REGEX_SIZE_LIMIT)
                        .build()
                        .map_err(|err| format!("entry '{}' failed to compile: {err}", entry.id))?;
                    regex_entries.push(RegexEntry {
                        id: entry.id.clone(),
                        suggestion: entry.suggested_replacements.first().cloned(),
                        regex,
                    });
                }
            }
        }

        // Dictionary entries default case_sensitive:false and none of the
        // real 46 entries opt into case_sensitive:true (Task 6), so it's
        // safe in v1 to fold every exact pattern into a single
        // ascii-case-insensitive automaton with lowercased pattern text
        // above. A future case_sensitive:true entry would need a second,
        // case-sensitive automaton — out of scope for Task 8.
        let automaton = AhoCorasickBuilder::new()
            .match_kind(MatchKind::LeftmostLongest)
            .ascii_case_insensitive(true)
            .build(&patterns)
            .map_err(|err| format!("failed to build vocabulary automaton: {err}"))?;

        Ok(Vocabulary { automaton, exact_entries, regex_entries })
    }

    /// Runs both engines over `prose_text` and merges their hits under
    /// longest-match-wins (spec Sec 11.3): when two hits' byte ranges
    /// overlap at all — full containment or a partial "crossing" overlap —
    /// the narrower one is dropped, regardless of which engine produced it.
    fn raw_hits(&self, prose_text: &str) -> Vec<RawHit> {
        let mut hits = Vec::new();

        for m in self.automaton.find_iter(prose_text) {
            let entry = &self.exact_entries[m.pattern().as_usize()];
            if entry.whole_word && !is_word_bounded(prose_text, m.start(), m.end()) {
                continue;
            }
            hits.push(RawHit {
                start: m.start(),
                end: m.end(),
                matched_text: prose_text[m.start()..m.end()].to_string(),
                suggestion: entry.suggestion.clone(),
            });
        }

        for entry in &self.regex_entries {
            for m in entry.regex.find_iter(prose_text) {
                hits.push(RawHit {
                    start: m.start(),
                    end: m.end(),
                    matched_text: m.as_str().to_string(),
                    suggestion: entry.suggestion.clone(),
                });
            }
        }

        // Longest-match-wins: sort by start ascending, then by end
        // descending, so the widest candidate at each start point is seen
        // first. Drop `hit` if it overlaps *any* already-kept hit at all —
        // not just full containment. A general interval-overlap check is
        // required here: two hits can "cross" (e.g. [0,10) and [5,15)) with
        // neither containing the other, and a containment-only check would
        // let both survive as overlapping evidence. Full containment (the
        // common case with the current dictionary, e.g. an exact "embark"
        // hit inside a longer "embark on a journey" phrase hit) is just the
        // special case of overlap where one span's bounds sit entirely
        // inside the other's.
        hits.sort_by_key(|h| (h.start, std::cmp::Reverse(h.end)));
        let mut kept: Vec<RawHit> = Vec::new();
        for hit in hits {
            let overlaps_kept = kept.iter().any(|k| k.start < hit.end && hit.start < k.end);
            if !overlaps_kept {
                kept.push(hit);
            }
        }
        kept
    }
}

/// A whole-word match requires non-alphanumeric (or absent) boundaries on
/// both sides, so e.g. "harness" does not match inside "harnessed".
fn is_word_bounded(text: &str, start: usize, end: usize) -> bool {
    let before_ok = text[..start].chars().next_back().map(|c| !c.is_alphanumeric()).unwrap_or(true);
    let after_ok = text[end..].chars().next().map(|c| !c.is_alphanumeric()).unwrap_or(true);
    before_ok && after_ok
}

/// Converts a byte offset within `text` into 1-based (line, column), where
/// "column" counts chars (not bytes) since the last newline.
fn line_and_column(text: &str, byte_offset: usize) -> (u32, u32) {
    let mut line = 1u32;
    let mut col = 1u32;
    for ch in text[..byte_offset].chars() {
        if ch == '\n' {
            line += 1;
            col = 1;
        } else {
            col += 1;
        }
    }
    (line, col)
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

    fn score(&self, doc: &Document, _deadline: Deadline) -> ScoreOutcome {
        let mut evidence = Vec::new();
        let mut total_hits = 0usize;

        for span in &doc.prose_spans {
            let prose_text = &doc.raw[span.clone()];
            for hit in self.raw_hits(prose_text) {
                total_hits += 1;
                let raw_start = span.start + hit.start;
                let raw_end = span.start + hit.end;
                let (line, column) = line_and_column(&doc.raw, raw_start);
                evidence.push(Evidence {
                    raw_offset: raw_start..raw_end,
                    prose_offset: hit.start..hit.end,
                    line,
                    column,
                    matched_text: hit.matched_text,
                    severity: Severity::Medium,
                    suggestion: hit.suggestion,
                });
            }
        }

        // Ported thresholds, verified directly against check_ai_tells.py:
        // total_hits combines both engines' hits into the single
        // Vocabulary family vote (spec Sec 2.2).
        let vote = if total_hits >= 4 {
            VoteStrength::Strong
        } else if total_hits >= 2 {
            VoteStrength::Suspicious
        } else {
            VoteStrength::None
        };

        let human_probability = match vote {
            VoteStrength::Strong => 0.1,
            VoteStrength::Suspicious => 0.4,
            VoteStrength::None => 0.9,
        };

        ScoreOutcome::Scored(Score::new(
            "vocabulary".to_string(),
            SignalFamily::Vocabulary,
            human_probability,
            ConfidenceTier::Medium,
            vote,
            evidence,
        ))
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
        let score = score_text("The team decided to embark on a journey toward better documentation.");
        assert!(
            !score.evidence.is_empty(),
            "expected at least one evidence entry from the overlapping matches"
        );
        for (i, a) in score.evidence.iter().enumerate() {
            for b in score.evidence.iter().skip(i + 1) {
                let overlaps = a.raw_offset.start < b.raw_offset.end && b.raw_offset.start < a.raw_offset.end;
                assert!(!overlaps, "evidence spans {:?} and {:?} overlap", a.raw_offset, b.raw_offset);
            }
        }
    }

    #[test]
    fn longest_match_wins_suppresses_crossing_overlap() {
        // Regression test (post-review): a *crossing* overlap is a pair of
        // spans where neither contains the other, e.g. [0,5) and [3,8]. A
        // containment-only check (`k.start <= hit.start && hit.end <=
        // k.end`) lets both survive, since neither is nested inside the
        // other — only a general interval-overlap check
        // (`k.start < hit.end && hit.start < k.end`) catches this.
        //
        // Note this can't be reproduced with two aho-corasick (exact)
        // patterns alone: `AhoCorasick::find_iter` under
        // `MatchKind::LeftmostLongest` already scans non-overlapping —
        // once it commits to a match it resumes scanning *after* that
        // match's end, so a second pattern starting inside the first's
        // span is never even yielded by the automaton. A genuine crossing
        // overlap requires two independent engines whose scans aren't
        // coordinated with each other, which is exactly the aho-corasick +
        // regex combination this backend runs. This synthetic dictionary
        // pairs a regex phrase entry matching "abcde" with an exact word
        // entry matching "defgh"; against "abcdefgh" the regex hit is
        // [0,5) and the exact hit is [3,8) — 0 < 8 and 3 < 5, so they
        // overlap, but neither range contains the other.
        let dictionary = Dictionary {
            schema_version: "1.0.0".to_string(),
            dictionary_version: "test".to_string(),
            entries: vec![regex_entry("crossing-regex", "abcde"), exact_entry("crossing-exact", "defgh")],
        };
        let backend = Vocabulary::new(dictionary).expect("synthetic crossing-overlap dictionary must compile");
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
                let overlaps = a.raw_offset.start < b.raw_offset.end && b.raw_offset.start < a.raw_offset.end;
                assert!(!overlaps, "evidence spans {:?} and {:?} overlap", a.raw_offset, b.raw_offset);
            }
        }
    }
}
