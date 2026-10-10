// src/backends/burstiness.rs
use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

const MIN_WORDS_FOR_STATS: usize = 150; // check_ai_tells.py MIN_WORDS_FOR_STATS
const MIN_SENTENCES: usize = 5; // check_ai_tells.py:38 (burstiness_ratio)
const VERY_LOW_BURSTINESS: f64 = 0.25;
const LOW_BURSTINESS_THRESHOLD: f64 = 0.35;

pub struct Burstiness;

fn population_stdev(values: &[usize]) -> f64 {
    let n = values.len() as f64;
    let mean = values.iter().sum::<usize>() as f64 / n;
    let variance = values
        .iter()
        .map(|&v| {
            let d = v as f64 - mean;
            d * d
        })
        .sum::<f64>()
        / n;
    variance.sqrt()
}

impl DetectorBackend for Burstiness {
    fn name(&self) -> &str {
        "burstiness"
    }
    fn family(&self) -> SignalFamily {
        SignalFamily::Burstiness
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

        let lengths: Vec<usize> = doc
            .sentences
            .iter()
            .map(|r| {
                unicode_segmentation::UnicodeSegmentation::unicode_words(&doc.prose[r.clone()])
                    .count()
            })
            .collect();
        if lengths.len() < MIN_SENTENCES {
            return ScoreOutcome::Abstained {
                reason: format!(
                    "only {} sentences, below the {MIN_SENTENCES}-sentence floor",
                    lengths.len()
                ),
            };
        }

        let mean = lengths.iter().sum::<usize>() as f64 / lengths.len() as f64;
        if mean == 0.0 {
            return ScoreOutcome::Abstained {
                reason: "mean sentence length is zero".to_string(),
            };
        }
        let ratio = population_stdev(&lengths) / mean;

        let vote = if ratio < VERY_LOW_BURSTINESS {
            VoteStrength::Strong
        } else if ratio < LOW_BURSTINESS_THRESHOLD {
            VoteStrength::Suspicious
        } else {
            VoteStrength::None
        };

        if deadline.expired() {
            return ScoreOutcome::Failed(crate::error::Error::Timeout);
        }
        let mut score = Score::new(
            "burstiness".to_string(),
            SignalFamily::Burstiness,
            ConfidenceTier::Medium,
            vote,
            vec![], // a document-level statistic; no line-anchored evidence
        )
        .metric(
            "sentence_length_cv",
            ratio,
            "ratio",
            "population-stdev/shared-segmentation-v1",
        );
        if vote != VoteStrength::None {
            score.document_findings.push(crate::score::DocumentFinding {rule_id:"statistics.burstiness".into(),severity:crate::score::Severity::Low,message:"Low document-wide variation in sentence word counts (uncalibrated heuristic).".into(),suggestion:Some("Review rhythm and readability in context; sentence uniformity does not establish authorship.".into()),suppression:None});
        }
        ScoreOutcome::Scored(score)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend::ScoreOutcome;
    use crate::deadline::Deadline;
    use crate::document::Document;
    use crate::score::VoteStrength;

    fn outcome_for(text: &str) -> ScoreOutcome {
        let backend = Burstiness;
        let doc = Document::from_stdin_text(text.to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        backend.score(&doc, deadline)
    }

    fn words(n: usize) -> String {
        (0..n)
            .map(|i| format!("word{i}"))
            .collect::<Vec<_>>()
            .join(" ")
    }

    #[test]
    fn short_document_abstains() {
        let outcome = outcome_for("Too short to measure burstiness on at all.");
        assert!(matches!(outcome, ScoreOutcome::Abstained { .. }));
    }

    #[test]
    fn under_150_words_abstains_even_with_many_sentences() {
        // 20 sentences of 5 words each = 100 words, well over 5 sentences but under 150 words
        let text = (0..20)
            .map(|_| "Five short words in sentence.".to_string())
            .collect::<Vec<_>>()
            .join(" ");
        let outcome = outcome_for(&text);
        assert!(
            matches!(outcome, ScoreOutcome::Abstained { .. }),
            "must abstain below the 150-word floor even with >=5 sentences"
        );
    }

    #[test]
    fn uniform_sentence_lengths_over_150_words_votes_strong() {
        // 31 sentences of exactly 6 words each = 186 words, stdev = 0 -> burstiness ratio 0.0
        let sentence = "This sentence has six words total.";
        let text = std::iter::repeat_n(sentence, 31)
            .collect::<Vec<_>>()
            .join(" ");
        let outcome = outcome_for(&text);
        match outcome {
            ScoreOutcome::Scored(score) => assert_eq!(score.vote, VoteStrength::Strong),
            _other => panic!("expected Scored, got abstain/fail"),
        }
        let _ = words(1); // silence unused helper warning if not otherwise used
    }

    #[test]
    fn over_150_words_but_under_5_sentences_abstains() {
        // 4 run-on sentences of 40 words each = 160 words (>=150), but only 4
        // sentences (<5) -- must abstain even though the word floor is cleared,
        // proving the sentence-count gate fires independently of the word-count gate.
        let text = (0..4)
            .map(|_| format!("{}.", words(40)))
            .collect::<Vec<_>>()
            .join(" ");
        let outcome = outcome_for(&text);
        assert!(
            matches!(outcome, ScoreOutcome::Abstained { .. }),
            "must abstain below the 5-sentence floor even with >=150 words"
        );
    }
}
