use crate::availability::Availability;
use crate::deadline::Deadline;
use crate::document::Document;
use crate::error::Error;
use crate::score::Score;

/// Independent signal family. Multiple backends may share a family; reduction grants at most one vote.
#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, serde::Deserialize, serde::Serialize,
)]
pub enum SignalFamily {
    Vocabulary,
    Punctuation,
    Burstiness,
    LexicalDiversity,
    Readability,
    Compression,
    /// Editorial observations; review only, never voting.
    Structure,
    /// Informational local-model evidence. Never eligible for a heuristic quorum vote.
    Model,
}

/// Distinguishes "not applicable to this input" (`Abstained`) from "something
/// broke" (`Failed`) — both excluded from the vote count in aggregation, but
/// `Failed` additionally surfaces as a `detect` warning (spec §2.1, §2.4).
#[derive(Debug, serde::Serialize)]
#[serde(tag = "status", content = "details", rename_all = "snake_case")]
pub enum ScoreOutcome {
    Scored(Score),
    Incomplete {
        score: Score,
        reason: Error,
        coverage: f64,
    },
    Abstained {
        reason: String,
        /// Typed model policy abstention; absent for heuristic backends.
        #[serde(skip_serializing_if = "Option::is_none")]
        model: Option<crate::models::ModelAbstention>,
    },
    Failed(Error),
}

pub trait DetectorBackend: Send + Sync {
    fn name(&self) -> &str;
    fn family(&self) -> SignalFamily;
    fn availability(&self) -> Availability;
    fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome;

    /// Opt-in local-model diagnostics. Heuristic backends retain their ordinary pass.
    fn score_full(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome {
        self.score(doc, deadline)
    }

    fn score_batch(&self, docs: &[Document], deadline: Deadline) -> Vec<ScoreOutcome> {
        docs.iter().map(|doc| self.score(doc, deadline)).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::deadline::Deadline;
    use crate::document::Document;

    struct AlwaysAbstains;
    impl DetectorBackend for AlwaysAbstains {
        fn name(&self) -> &str {
            "always-abstains"
        }
        fn family(&self) -> SignalFamily {
            SignalFamily::Vocabulary
        }
        fn availability(&self) -> crate::availability::Availability {
            crate::availability::Availability::Ready
        }
        fn score(&self, _doc: &Document, _deadline: Deadline) -> ScoreOutcome {
            ScoreOutcome::Abstained {
                reason: "test backend".into(),
                model: None,
            }
        }
    }

    #[test]
    fn default_score_batch_maps_score_over_documents() {
        let backend = AlwaysAbstains;
        let docs = vec![
            Document::from_stdin_text("one".into(), false),
            Document::from_stdin_text("two".into(), false),
        ];
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        let outcomes = backend.score_batch(&docs, deadline);
        assert_eq!(outcomes.len(), 2);
        for outcome in outcomes {
            assert!(matches!(outcome, ScoreOutcome::Abstained { .. }));
        }
    }
}
