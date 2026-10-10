// src/backends/punctuation.rs
use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

pub struct Punctuation;

impl DetectorBackend for Punctuation {
    fn name(&self) -> &str {
        "punctuation"
    }
    fn family(&self) -> SignalFamily {
        SignalFamily::Punctuation
    }
    fn availability(&self) -> Availability {
        Availability::Ready
    }

    fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome {
        self.score_limited(doc, deadline, 10_000)
    }
}
impl Punctuation {
    pub fn score_limited(&self, doc: &Document, deadline: Deadline, cap: usize) -> ScoreOutcome {
        if deadline.expired() {
            return ScoreOutcome::Failed(crate::error::Error::Timeout);
        }
        let word_count = doc.words.len();
        let em_dash_count = doc.prose.matches('\u{2014}').count();

        let vote = if em_dash_count >= 6 && em_dash_count as f64 > word_count as f64 / 100.0 {
            VoteStrength::Strong
        } else if em_dash_count >= 3 && em_dash_count as f64 > word_count as f64 / 150.0 {
            VoteStrength::Suspicious
        } else {
            VoteStrength::None
        };

        let mut evidence = vec![];
        let mut failure = None;
        let mut covered = 0;
        if vote != VoteStrength::None {
            for (i, _) in doc.prose.match_indices('—') {
                if deadline.expired() {
                    failure = Some(crate::error::Error::Timeout);
                    break;
                }
                if evidence.len() >= cap {
                    failure = Some(crate::error::Error::ResourceLimit(
                        "punctuation candidate budget".into(),
                    ));
                    break;
                }
                covered = i + 3;
                evidence.push(doc.finding(
                    i..i + 3,
                    "punctuation.em-dash-density",
                    Some("Consider a comma, period, or parentheses where appropriate.".into()),
                ));
            }
        }

        let mut score = Score::new(
            "punctuation".to_string(),
            SignalFamily::Punctuation,
            ConfidenceTier::Medium,
            vote,
            evidence,
        )
        .metric(
            "prose_words",
            word_count as f64,
            "words",
            "unicode-segmentation-v1",
        )
        .metric(
            "em_dash_count",
            em_dash_count as f64,
            "occurrences",
            "prepared-prose-v1",
        )
        .metric(
            "em_dashes_per_100_words",
            em_dash_count as f64 * 100.0 / word_count.max(1) as f64,
            "occurrences/100-words",
            "prepared-prose-v1",
        );
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::deadline::Deadline;
    use crate::document::Document;
    use crate::score::VoteStrength;

    fn score_text(text: &str) -> crate::score::Score {
        let backend = Punctuation;
        let doc = Document::from_stdin_text(text.to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        match backend.score(&doc, deadline) {
            crate::backend::ScoreOutcome::Scored(score) => score,
            _ => panic!("expected Scored"),
        }
    }

    #[test]
    fn no_em_dashes_votes_none() {
        let score = score_text("A plain sentence with no unusual punctuation at all here.");
        assert_eq!(score.vote, VoteStrength::None);
    }

    #[test]
    fn high_em_dash_density_votes_strong() {
        // 100 words, 7 em dashes -> 7 >= 6 and 7 > 100/100 (1.0)
        let words: Vec<String> = (0..100).map(|i| format!("w{i}")).collect();
        let mut text = words.join(" ");
        for _ in 0..7 {
            text.push_str(" — ");
        }
        let score = score_text(&text);
        assert_eq!(score.vote, VoteStrength::Strong);
    }

    #[test]
    fn moderate_em_dash_density_votes_suspicious() {
        // 150 words, 4 em dashes -> 4 >= 3 and 4 > 150/150 (1.0), but < 6 so not Strong
        let words: Vec<String> = (0..150).map(|i| format!("w{i}")).collect();
        let mut text = words.join(" ");
        for _ in 0..4 {
            text.push_str(" — ");
        }
        let score = score_text(&text);
        assert_eq!(score.vote, VoteStrength::Suspicious);
    }
}
