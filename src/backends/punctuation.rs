// src/backends/punctuation.rs
use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

pub struct Punctuation;

impl DetectorBackend for Punctuation {
    fn name(&self) -> &str { "punctuation" }
    fn family(&self) -> SignalFamily { SignalFamily::Punctuation }
    fn availability(&self) -> Availability { Availability::Ready }

    fn score(&self, doc: &Document, _deadline: Deadline) -> ScoreOutcome {
        let word_count = doc.raw.split_whitespace().count();
        let em_dash_count = doc.raw.matches('\u{2014}').count();

        let vote = if em_dash_count >= 6 && em_dash_count as f64 > word_count as f64 / 100.0 {
            VoteStrength::Strong
        } else if em_dash_count >= 3 && em_dash_count as f64 > word_count as f64 / 150.0 {
            VoteStrength::Suspicious
        } else {
            VoteStrength::None
        };

        let human_probability = match vote {
            VoteStrength::Strong => 0.15,
            VoteStrength::Suspicious => 0.4,
            VoteStrength::None => 0.9,
        };

        ScoreOutcome::Scored(Score::new(
            "punctuation".to_string(),
            SignalFamily::Punctuation,
            human_probability,
            ConfidenceTier::Medium,
            vote,
            vec![], // density counting is not a per-location match; no line-anchored evidence to report
        ))
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
