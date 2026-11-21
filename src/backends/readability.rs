// src/backends/readability.rs
use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

const MIN_WORDS_FOR_STATS: usize = 150;

pub struct Readability;

/// Approximate English syllables from vowel groups and a terminal-e adjustment.
/// Trims surrounding nonletters; not a pronunciation dictionary.
pub(crate) fn count_syllables(word: &str) -> usize {
    let word = word
        .trim_matches(|c: char| !c.is_alphabetic())
        .to_lowercase();
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

#[cfg(test)]
fn count_sentences(text: &str) -> usize {
    let blocks = std::iter::once(0..text.len()).collect::<Vec<_>>();
    crate::document::sentence_ranges(text, &blocks).len().max(1)
}

#[cfg(test)]
pub(crate) fn flesch_kincaid_grade(text: &str) -> f64 {
    let words: Vec<&str> = unicode_segmentation::UnicodeSegmentation::unicode_words(text).collect();
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

    fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome {
        if deadline.expired() {
            return ScoreOutcome::Failed(crate::error::Error::Timeout);
        }
        let word_count = doc.words.len();
        if word_count < MIN_WORDS_FOR_STATS {
            return ScoreOutcome::Abstained {
                reason: format!(
                    "text has {word_count} words, below the {MIN_WORDS_FOR_STATS}-word floor"
                ),
                model: None,
            };
        }

        let prose = &doc.prose;

        if !doc.english_supported() {
            return ScoreOutcome::Abstained {
                reason: doc.language.reason.clone(),
                model: None,
            };
        }

        let mut syllables: usize = 0;
        for word_range in &doc.words {
            if deadline.expired() {
                return ScoreOutcome::Failed(crate::error::Error::Timeout);
            }
            syllables += count_syllables(&prose[word_range.clone()]);
        }
        let grade = 0.39 * doc.words.len() as f64 / doc.sentences.len().max(1) as f64
            + 11.8 * syllables as f64 / doc.words.len() as f64
            - 15.59;

        // Evidence-only in v1 (spec §2.2, §7 item 5): always VoteStrength::None.

        if deadline.expired() {
            return ScoreOutcome::Failed(crate::error::Error::Timeout);
        }
        ScoreOutcome::Scored(
            Score::new(
                "readability".to_string(),
                SignalFamily::Readability,
                ConfidenceTier::Low,
                VoteStrength::None,
                vec![],
            )
            .metric(
                "flesch_kincaid_grade",
                grade,
                "grade",
                "vowel-groups/shared-segmentation-v1",
            ),
        )
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
        assert_eq!(count_syllables("time"), 1);
        assert_eq!(count_syllables("time."), 1);
        assert_eq!(count_syllables(r#""time""#), 1);
        assert_eq!(count_syllables("TIME"), 1);
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
        assert!(matches!(
            backend.score(&doc, deadline),
            ScoreOutcome::Abstained { .. }
        ));
    }

    #[test]
    fn evidence_only_never_votes_above_none() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        use crate::score::VoteStrength;
        let backend = Readability;
        let text = "The quick brown fox jumps over the lazy dog. ".repeat(30);
        let mut doc = Document::from_stdin_text(text, false);
        doc.assert_language(Some("en"));
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        let ScoreOutcome::Scored(score) = backend.score(&doc, deadline) else {
            panic!("Readability must score supported English above the word floor")
        };
        assert_eq!(score.vote, VoteStrength::None);
    }

    #[test]
    fn pinned_textstat_fixtures() {
        let root: serde_json::Value = serde_json::from_str(include_str!(
            "../../tests/fixtures/readability-reference.json"
        ))
        .unwrap();
        let cases = root["cases"].as_array().unwrap();
        assert_eq!(cases.len(), 6);
        for case in cases {
            let id = case["id"].as_str().unwrap();
            let text = case["sentence_group"]
                .as_str()
                .unwrap()
                .repeat(case["repetitions"].as_u64().unwrap() as usize);
            let mut doc = Document::from_stdin_text(text.clone(), false);
            doc.assert_language(Some("en"));
            assert_eq!(
                doc.words.len(),
                case["expected_native_words"].as_u64().unwrap() as usize,
                "{id}"
            );
            assert_eq!(
                doc.sentences.len(),
                case["expected_native_sentences"].as_u64().unwrap() as usize,
                "{id}"
            );
            let ScoreOutcome::Scored(score) =
                Readability.score(&doc, Deadline::new(std::time::Duration::from_secs(5)))
            else {
                panic!("{id}: readability did not score")
            };
            let actual = score.metrics["flesch_kincaid_grade"].value;
            let expected = case["expected_native_grade"].as_f64().unwrap();
            let reference = case["reference_grade"].as_f64().unwrap();
            let difference = case["expected_grade_difference"].as_f64().unwrap();
            assert!(
                (actual - expected).abs() < 1e-9,
                "{id}: {actual} vs {expected}"
            );
            assert!(
                (actual - reference - difference).abs() < 1e-9,
                "{id}: changed reference difference"
            );
            assert!(
                (flesch_kincaid_grade(&text) - actual).abs() < 1e-9,
                "{id}: helper/backend disagree"
            );
            assert_eq!(score.vote, VoteStrength::None, "{id}");
        }
    }
}
