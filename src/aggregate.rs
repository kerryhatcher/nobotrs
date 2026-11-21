use crate::{
    backend::{ScoreOutcome, SignalFamily},
    error::Error,
    score::{Score, VoteStrength},
};
use serde::Serialize;
use std::collections::{BTreeMap, HashSet};
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Verdict {
    Flagged,
    Clean,
    Inconclusive,
}
#[derive(Debug, Clone, Serialize)]
pub struct Warning {
    pub family: SignalFamily,
    pub error: Error,
}
#[derive(Debug, Clone, Serialize)]
pub struct FamilyDecision {
    pub family: SignalFamily,
    pub vote: VoteStrength,
    pub backends: Vec<String>,
}
#[derive(Debug, Serialize)]
pub struct AggregationResult {
    pub verdict: Verdict,
    pub votes_cast: usize,
    pub warnings: Vec<Warning>,
    pub scores: Vec<Score>,
    pub outcomes: Vec<(SignalFamily, ScoreOutcome)>,
    pub families: Vec<FamilyDecision>,
}
/// Eligible backends in a family reduce to their strongest vote (at most one contribution).
/// Failed/informational/abstained backends never increase participation.
pub fn aggregate(
    outcomes: Vec<(SignalFamily, ScoreOutcome)>,
    quorum: usize,
) -> Result<AggregationResult, String> {
    if !(1..=3).contains(&quorum) {
        return Err("quorum must be between 1 and 3 eligible core families".into());
    }
    let mut names = HashSet::new();
    let mut decisions: BTreeMap<SignalFamily, FamilyDecision> = BTreeMap::new();
    let mut warnings = vec![];
    let mut scores = vec![];
    for (family, outcome) in &outcomes {
        match outcome {
            ScoreOutcome::Scored(score) => {
                if score.metrics.values().any(|m| !m.value.is_finite()) {
                    return Err("nonfinite metric".into());
                }
                if score.family != *family {
                    return Err("score family mismatch".into());
                }
                if !names.insert(&score.backend) {
                    return Err("duplicate backend identity".into());
                }
                if score.voting_eligible && *family != SignalFamily::Model {
                    let d = decisions.entry(*family).or_insert(FamilyDecision {
                        family: *family,
                        vote: VoteStrength::None,
                        backends: vec![],
                    });
                    d.vote = d.vote.max(score.vote);
                    d.backends.push(score.backend.clone());
                }
                scores.push(score.clone());
            }
            ScoreOutcome::Incomplete { score, reason, .. } => {
                scores.push(score.clone());
                warnings.push(Warning {
                    family: *family,
                    error: reason.clone(),
                });
            }
            ScoreOutcome::Failed(error) => warnings.push(Warning {
                family: *family,
                error: error.clone(),
            }),
            ScoreOutcome::Abstained { .. } => {}
        }
    }
    let families: Vec<_> = decisions.into_values().collect();
    let votes_cast = families.len();
    let agreeing = families
        .iter()
        .filter(|d| d.vote != VoteStrength::None)
        .count();
    let verdict = if votes_cast < quorum {
        Verdict::Inconclusive
    } else if agreeing >= quorum {
        Verdict::Flagged
    } else {
        Verdict::Clean
    };
    Ok(AggregationResult {
        verdict,
        votes_cast,
        warnings,
        scores,
        outcomes,
        families,
    })
}

/// Adapter-facing entry point validates identities for failures and abstentions too.
pub struct BackendOutcome {
    pub backend: String,
    pub family: SignalFamily,
    pub outcome: ScoreOutcome,
}
pub fn aggregate_backends(
    outcomes: Vec<BackendOutcome>,
    quorum: usize,
) -> Result<AggregationResult, String> {
    let mut names = HashSet::new();
    for item in &outcomes {
        if item.backend.is_empty() || !names.insert(&item.backend) {
            return Err("empty or duplicate backend identity".into());
        }
        if let ScoreOutcome::Scored(score) | ScoreOutcome::Incomplete { score, .. } = &item.outcome
        {
            if score.backend != item.backend || score.family != item.family {
                return Err("backend outcome identity mismatch".into());
            }
        }
    }
    aggregate(
        outcomes
            .into_iter()
            .map(|b| (b.family, b.outcome))
            .collect(),
        quorum,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{backend::SignalFamily, score::Score};

    #[test]
    fn model_family_is_never_reduced_into_a_vote() {
        let mut score = Score::new(
            "desklib".into(),
            SignalFamily::Model,
            crate::score::ConfidenceTier::Low,
            VoteStrength::Strong,
            vec![],
        );
        // Even a malformed model score cannot become quorum participation.
        score.voting_eligible = true;
        let result = aggregate(vec![(SignalFamily::Model, ScoreOutcome::Scored(score))], 1)
            .expect("aggregation");
        assert!(result.families.is_empty());
        assert_eq!(result.votes_cast, 0);
        assert_eq!(result.verdict, Verdict::Inconclusive);
    }
}
