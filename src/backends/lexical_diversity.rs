// src/backends/lexical_diversity.rs
use unicode_segmentation::UnicodeSegmentation;

use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

const MIN_WORDS_FOR_STATS: usize = 150; // check_ai_tells.py MIN_WORDS_FOR_STATS -- the effective floor
const MTLD_THRESHOLD: f64 = 0.72;

pub struct LexicalDiversity;

#[cfg(test)]
pub(crate) fn tokenize(text: &str) -> Vec<String> {
    text.unicode_words().map(|w| w.to_lowercase()).collect()
}

/// Standard MTLD (McCarthy & Jarvis, 2010): walk tokens accumulating a
/// running type-token ratio; each time it drops to/below `threshold`, close
/// a "factor" and reset. A leftover partial segment contributes a fractional
/// factor. Run forward and reverse, average the two — matching the algorithm
/// `lexicalrichness.mtld()` (used by `check_ai_tells.py`) implements.
#[cfg(test)]
pub(crate) fn mtld(tokens: &[String], threshold: f64) -> f64 {
    mtld_budget(tokens, threshold, None).unwrap()
}
fn mtld_budget(tokens: &[String], threshold: f64, deadline: Option<Deadline>) -> Option<f64> {
    if tokens.is_empty() {
        return Some(0.0);
    }
    let forward = mtld_single_pass(tokens, threshold, deadline)?;
    let mut reversed = Vec::with_capacity(tokens.len());
    for token in tokens.iter().rev() {
        if deadline.is_some_and(|d| d.expired()) {
            return None;
        }
        reversed.push(token.clone());
    }
    let backward = mtld_single_pass(&reversed, threshold, deadline)?;
    Some((forward + backward) / 2.0)
}

fn mtld_single_pass(tokens: &[String], threshold: f64, deadline: Option<Deadline>) -> Option<f64> {
    use std::collections::HashSet;
    let mut factor_count = 0.0_f64;
    let mut segment_len = 0usize;
    let mut types: HashSet<&str> = HashSet::new();

    for token in tokens {
        if deadline.is_some_and(|d| d.expired()) {
            return None;
        }
        types.insert(token.as_str());
        segment_len += 1;
        let ttr = types.len() as f64 / segment_len as f64;
        if ttr <= threshold {
            factor_count += 1.0;
            types.clear();
            segment_len = 0;
        }
    }

    if segment_len > 0 {
        let ttr = types.len() as f64 / segment_len as f64;
        let partial = (1.0 - ttr) / (1.0 - threshold);
        factor_count += partial;
    }

    if factor_count == 0.0 {
        Some(tokens.len() as f64)
    } else {
        Some(tokens.len() as f64 / factor_count)
    }
}

impl DetectorBackend for LexicalDiversity {
    fn name(&self) -> &str {
        "lexical-diversity"
    }
    fn family(&self) -> SignalFamily {
        SignalFamily::LexicalDiversity
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
            };
        }

        let prose = &doc.prose;

        if !doc.english_supported() {
            return ScoreOutcome::Abstained {
                reason: doc.language.reason.clone(),
            };
        }

        let mut tokens: Vec<String> = Vec::new();
        for word in prose.unicode_words() {
            if deadline.expired() {
                return ScoreOutcome::Failed(crate::error::Error::Timeout);
            }
            tokens.push(word.to_lowercase());
        }
        let Some(mtld_score) = mtld_budget(&tokens, MTLD_THRESHOLD, Some(deadline)) else {
            return ScoreOutcome::Failed(crate::error::Error::Timeout);
        };

        // Evidence-only in v1 (spec §2.2, §7 item 5): always VoteStrength::None.

        if deadline.expired() {
            return ScoreOutcome::Failed(crate::error::Error::Timeout);
        }
        ScoreOutcome::Scored(
            Score::new(
                "lexical-diversity".to_string(),
                SignalFamily::LexicalDiversity,
                ConfidenceTier::Low,
                VoteStrength::None,
                vec![],
            )
            .metric(
                "mtld",
                mtld_score,
                "tokens/factor",
                "bidirectional-mtld-0.72-v1",
            ),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mtld_matches_lexicalrichness_reference_vector() {
        // Fixture text and expected value captured from a real run of:
        //   uv run --with lexicalrichness python3 -c "
        //   from lexicalrichness import LexicalRichness
        //   text = ('The quick brown fox jumps over the lazy dog. ' * 1) + \
        //          'A completely different sentence follows using entirely distinct words now. ' + \
        //          'Yet another unique sentence continues the passage onward here. ' + \
        //          'Repetition of the the the the the fills this next portion up. ' * 3
        //   print(LexicalRichness(text).mtld(threshold=0.72))
        //   "
        // Printed output: 19.91300488237905
        let fixture_text = "The quick brown fox jumps over the lazy dog. \
            A completely different sentence follows using entirely distinct words now. \
            Yet another unique sentence continues the passage onward here. \
            Repetition of the the the the the fills this next portion up. \
            Repetition of the the the the the fills this next portion up. \
            Repetition of the the the the the fills this next portion up. ";
        let reference_mtld = 19.91300488237905_f64;
        let tokens = tokenize(fixture_text);
        let computed = mtld(&tokens, 0.72);
        assert!(
            (computed - reference_mtld).abs() < reference_mtld * 0.05 + 1.0,
            "computed MTLD {computed} diverges from reference {reference_mtld} by more than 5%+1.0 tolerance"
        );
    }

    #[test]
    fn identical_repeated_word_has_low_mtld() {
        let tokens = tokenize(&"same ".repeat(200));
        let computed = mtld(&tokens, 0.72);
        assert!(
            computed < 5.0,
            "a text with zero lexical variety should have very low MTLD, got {computed}"
        );
    }

    #[test]
    fn all_unique_words_has_high_mtld() {
        let text = (0..200)
            .map(|i| format!("uniqueword{i}"))
            .collect::<Vec<_>>()
            .join(" ");
        let tokens = tokenize(&text);
        let computed = mtld(&tokens, 0.72);
        assert!(
            computed > 100.0,
            "an all-unique-word text should have very high MTLD, got {computed}"
        );
    }

    #[test]
    fn under_150_words_abstains() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        let backend = LexicalDiversity;
        let doc = Document::from_stdin_text("only a few words here total".to_string(), false);
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
        let backend = LexicalDiversity;
        let text = "same ".repeat(200); // deliberately low-diversity, over the word floor
        let doc = Document::from_stdin_text(text, false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        if let ScoreOutcome::Scored(score) = backend.score(&doc, deadline) {
            assert_eq!(
                score.vote,
                VoteStrength::None,
                "LexicalDiversity must never vote above None in v1 (evidence-only, spec §7 item 5)"
            );
        }
    }
}
