// src/aggregate.rs
use crate::backend::{ScoreOutcome, SignalFamily};
use crate::error::Error;
use crate::score::{Score, VoteStrength};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    Flagged,
    Clean,
    Inconclusive,
}

#[derive(Debug, Clone)]
pub struct Warning {
    pub family: SignalFamily,
    pub error: Error,
}

#[derive(Debug)]
pub struct AggregationResult {
    pub verdict: Verdict,
    pub votes_cast: usize,
    pub warnings: Vec<Warning>,
    pub scores: Vec<Score>,
}

/// Aggregates one `ScoreOutcome` per enabled family into a quorum verdict
/// (spec §2.4). `votes_cast` counts every family that returned `Scored(_)`
/// regardless of vote strength — a family that scored and found nothing
/// suspicious still completed a real analysis; only `Abstained`/`Failed` are
/// non-participation. If `votes_cast < quorum`, the verdict is `Inconclusive`
/// regardless of what the families that did vote said (spec §2.4).
pub fn aggregate(outcomes: Vec<(SignalFamily, ScoreOutcome)>, quorum: usize) -> AggregationResult {
    let mut votes_cast = 0usize;
    let mut agreeing = 0usize;
    let mut warnings = Vec::new();
    let mut scores = Vec::new();

    for (family, outcome) in outcomes {
        match outcome {
            ScoreOutcome::Scored(score) => {
                votes_cast += 1;
                if matches!(score.vote, VoteStrength::Suspicious | VoteStrength::Strong) {
                    agreeing += 1;
                }
                scores.push(score);
            }
            ScoreOutcome::Abstained { .. } => {}
            ScoreOutcome::Failed(error) => {
                warnings.push(Warning { family, error });
            }
        }
    }

    let verdict = if votes_cast < quorum {
        Verdict::Inconclusive
    } else if agreeing >= quorum {
        Verdict::Flagged
    } else {
        Verdict::Clean
    };

    AggregationResult { verdict, votes_cast, warnings, scores }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend::{ScoreOutcome, SignalFamily};
    use crate::error::Error;
    use crate::score::{ConfidenceTier, Score, VoteStrength};

    fn scored(family: SignalFamily, vote: VoteStrength) -> ScoreOutcome {
        ScoreOutcome::Scored(Score::new(format!("{:?}", family), family, 0.5, ConfidenceTier::Medium, vote, vec![]))
    }

    #[test]
    fn two_of_three_strong_votes_flags() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, scored(SignalFamily::Vocabulary, VoteStrength::Strong)),
            (SignalFamily::Punctuation, scored(SignalFamily::Punctuation, VoteStrength::Strong)),
            (SignalFamily::Burstiness, scored(SignalFamily::Burstiness, VoteStrength::None)),
        ];
        let result = aggregate(outcomes, 2);
        assert_eq!(result.verdict, Verdict::Flagged);
        assert_eq!(result.votes_cast, 3);
        assert!(result.warnings.is_empty());
    }

    #[test]
    fn one_of_three_suspicious_stays_clean() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, scored(SignalFamily::Vocabulary, VoteStrength::Suspicious)),
            (SignalFamily::Punctuation, scored(SignalFamily::Punctuation, VoteStrength::None)),
            (SignalFamily::Burstiness, scored(SignalFamily::Burstiness, VoteStrength::None)),
        ];
        let result = aggregate(outcomes, 2);
        assert_eq!(result.verdict, Verdict::Clean);
    }

    #[test]
    fn abstained_and_failed_do_not_count_toward_votes_cast() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, scored(SignalFamily::Vocabulary, VoteStrength::Strong)),
            (SignalFamily::Punctuation, ScoreOutcome::Abstained { reason: "n/a".into() }),
            (SignalFamily::Burstiness, ScoreOutcome::Failed(Error::InternalError("boom".into()))),
        ];
        let result = aggregate(outcomes, 2);
        assert_eq!(result.votes_cast, 1);
        assert_eq!(result.verdict, Verdict::Inconclusive, "only 1 vote_cast < quorum 2 -> Inconclusive even though the one vote was Strong");
    }

    #[test]
    fn failed_backend_populates_warnings() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, scored(SignalFamily::Vocabulary, VoteStrength::None)),
            (SignalFamily::Punctuation, scored(SignalFamily::Punctuation, VoteStrength::None)),
            (SignalFamily::Burstiness, ScoreOutcome::Failed(Error::ModelLoadFailed("corrupt".into()))),
        ];
        let result = aggregate(outcomes, 2);
        assert_eq!(result.warnings.len(), 1);
        assert_eq!(result.warnings[0].family, SignalFamily::Burstiness);
    }

    #[test]
    fn clean_with_warnings_is_still_clean_verdict_but_nonempty_warnings() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, scored(SignalFamily::Vocabulary, VoteStrength::None)),
            (SignalFamily::Punctuation, scored(SignalFamily::Punctuation, VoteStrength::None)),
            (SignalFamily::Burstiness, ScoreOutcome::Failed(Error::NetworkError("timeout".into()))),
        ];
        // Only 2 votes_cast (Vocabulary, Punctuation) meets quorum=2, both None -> Clean.
        let result = aggregate(outcomes, 2);
        assert_eq!(result.verdict, Verdict::Clean);
        assert_eq!(result.warnings.len(), 1);
    }

    #[test]
    fn zero_votes_cast_is_inconclusive_not_clean() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, ScoreOutcome::Abstained { reason: "n/a".into() }),
            (SignalFamily::Punctuation, ScoreOutcome::Abstained { reason: "n/a".into() }),
        ];
        let result = aggregate(outcomes, 2);
        assert_eq!(result.verdict, Verdict::Inconclusive);
    }
}
