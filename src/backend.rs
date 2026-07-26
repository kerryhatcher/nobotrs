use crate::availability::Availability;
use crate::deadline::Deadline;
use crate::document::Document;
use crate::error::Error;
use crate::score::Score;

/// Which independent signal family a backend's vote belongs to (spec §2.2).
/// One `DetectorBackend` instance produces exactly one family's vote — a tier
/// that covers several families registers one backend instance per family,
/// not one backend that multiplexes several (spec §2.1).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Deserialize)]
pub enum SignalFamily {
    Vocabulary,
    Punctuation,
    Burstiness,
    LexicalDiversity,
    Readability,
    Compression,
}

/// Distinguishes "not applicable to this input" (`Abstained`) from "something
/// broke" (`Failed`) — both excluded from the vote count in aggregation, but
/// `Failed` additionally surfaces as a `detect` warning (spec §2.1, §2.4).
pub enum ScoreOutcome {
    Scored(Score),
    Abstained { reason: String },
    Failed(Error),
}

pub trait DetectorBackend: Send + Sync {
    fn name(&self) -> &str;
    fn family(&self) -> SignalFamily;
    fn availability(&self) -> Availability;
    fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome;

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
        fn name(&self) -> &str { "always-abstains" }
        fn family(&self) -> SignalFamily { SignalFamily::Vocabulary }
        fn availability(&self) -> crate::availability::Availability { crate::availability::Availability::Ready }
        fn score(&self, _doc: &Document, _deadline: Deadline) -> ScoreOutcome {
            ScoreOutcome::Abstained { reason: "test backend".into() }
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
