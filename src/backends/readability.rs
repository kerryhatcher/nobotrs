// src/backends/readability.rs
use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

const MIN_WORDS_FOR_STATS: usize = 150;

pub struct Readability;

/// Standard vowel-group syllable-counting heuristic: count transitions into a
/// vowel group, then drop one for a silent trailing "e" (when that leaves at
/// least one syllable). Not bit-identical to any specific library's counter —
/// validated against `textstat`'s output within a stated tolerance instead
/// (see Task 12's Step 1/2), since matching the standard Flesch-Kincaid
/// formula's grade-level ballpark is the actual correctness bar (spec §8, §10).
pub(crate) fn count_syllables(word: &str) -> usize {
    let word = word.to_lowercase();
    let is_vowel = |c: char| matches!(c, 'a' | 'e' | 'i' | 'o' | 'u' | 'y');
    let mut count = 0usize;
    let mut prev_was_vowel = false;
    for c in word.chars() {
        let v = is_vowel(c);
        if v && !prev_was_vowel {
            count += 1;
        }
        prev_was_vowel = v;
    }
    if word.ends_with('e') && count > 1 {
        count -= 1;
    }
    count.max(1)
}

fn count_sentences(text: &str) -> usize {
    let count = text.matches(['.', '!', '?']).count();
    count.max(1)
}

pub(crate) fn flesch_kincaid_grade(text: &str) -> f64 {
    let words: Vec<&str> = text.split_whitespace().collect();
    let word_count = words.len().max(1) as f64;
    let sentence_count = count_sentences(text) as f64;
    let syllable_count: usize = words.iter().map(|w| count_syllables(w)).sum();

    0.39 * (word_count / sentence_count) + 11.8 * (syllable_count as f64 / word_count) - 15.59
}

impl DetectorBackend for Readability {
    fn name(&self) -> &str {
        "readability"
    }
    fn family(&self) -> SignalFamily {
        SignalFamily::Readability
    }
    fn availability(&self) -> Availability {
        Availability::Ready
    }

    fn score(&self, doc: &Document, _deadline: Deadline) -> ScoreOutcome {
        let word_count = doc.raw.split_whitespace().count();
        if word_count < MIN_WORDS_FOR_STATS {
            return ScoreOutcome::Abstained {
                reason: format!(
                    "text has {word_count} words, below the {MIN_WORDS_FOR_STATS}-word floor"
                ),
            };
        }

        let prose: String = doc
            .prose_spans
            .iter()
            .map(|s| &doc.raw[s.clone()])
            .collect::<Vec<_>>()
            .join(" ");

        if let Ok(lang) = std::panic::catch_unwind(|| whichlang::detect_language(&prose)) {
            if lang != whichlang::Lang::Eng {
                return ScoreOutcome::Abstained {
                    reason: "non-English text; Flesch-Kincaid is English-syllable-tuned"
                        .to_string(),
                };
            }
        }

        let grade = flesch_kincaid_grade(&prose);

        // Evidence-only in v1 (spec §2.2, §7 item 5): always VoteStrength::None.
        let human_probability = (1.0 - (grade / 20.0).clamp(0.0, 1.0)) as f32;

        ScoreOutcome::Scored(Score::new(
            "readability".to_string(),
            SignalFamily::Readability,
            human_probability,
            ConfidenceTier::Low,
            VoteStrength::None,
            vec![],
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn syllable_count_handles_common_cases() {
        assert_eq!(count_syllables("cat"), 1);
        assert_eq!(count_syllables("running"), 2);
        assert_eq!(count_syllables("beautiful"), 3);
        assert_eq!(count_syllables("the"), 1);
        assert_eq!(count_syllables("time"), 1); // silent trailing e
    }

    #[test]
    fn grade_level_matches_textstat_reference_within_tolerance() {
        let text = "The quick brown fox jumps over the lazy dog while the sun sets slowly behind the distant hills. ".repeat(15);
        // Reference value captured from a real run of:
        //   uv run --with textstat python3 -c "
        //   import textstat
        //   text = 'The quick brown fox jumps over the lazy dog while the sun sets slowly behind the distant hills. ' * 15
        //   print(textstat.flesch_kincaid_grade(text))
        //   "
        // Printed output: 6.507777777777779
        let reference_grade = 6.507777777777779_f64;
        let grade = flesch_kincaid_grade(&text);
        assert!(
            (grade - reference_grade).abs() < 1.5,
            "computed grade {grade} diverges from textstat reference {reference_grade} by more than 1.5"
        );
    }

    #[test]
    fn under_150_words_abstains() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        let backend = Readability;
        let doc = Document::from_stdin_text("just a few words".to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        assert!(matches!(backend.score(&doc, deadline), ScoreOutcome::Abstained { .. }));
    }

    #[test]
    fn evidence_only_never_votes_above_none() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        use crate::score::VoteStrength;
        let backend = Readability;
        let text = "The quick brown fox jumps over the lazy dog. ".repeat(30);
        let doc = Document::from_stdin_text(text, false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        if let ScoreOutcome::Scored(score) = backend.score(&doc, deadline) {
            assert_eq!(score.vote, VoteStrength::None);
        }
    }
}
