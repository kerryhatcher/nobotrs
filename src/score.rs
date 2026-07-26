use std::ops::Range;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Severity {
    Low,
    Medium,
    High,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConfidenceTier {
    Low,
    Medium,
    High,
}

/// The discrete per-family strength a `Score` contributes to aggregation
/// (spec §2.4). `None` means "this family scored the document and found
/// nothing suspicious" — distinct from `ScoreOutcome::Abstained`, which means
/// the backend never scored the document at all (§2.1, §2.4).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VoteStrength {
    None,
    Suspicious,
    Strong,
}

#[derive(Debug, Clone)]
pub struct Evidence {
    pub raw_offset: Range<usize>,
    pub prose_offset: Range<usize>,
    pub line: u32,
    pub column: u32,
    pub matched_text: String,
    pub severity: Severity,
    pub suggestion: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Score {
    pub backend: String,
    pub family: crate::backend::SignalFamily,
    pub human_probability: f32,
    pub confidence: ConfidenceTier,
    pub vote: VoteStrength,
    pub evidence: Vec<Evidence>,
}

impl Score {
    pub fn new(
        backend: String,
        family: crate::backend::SignalFamily,
        human_probability: f32,
        confidence: ConfidenceTier,
        vote: VoteStrength,
        evidence: Vec<Evidence>,
    ) -> Score {
        Score {
            backend,
            family,
            human_probability: Self::clamp_probability(human_probability),
            confidence,
            vote,
            evidence,
        }
    }

    /// `human_probability` must never be NaN or infinite (spec §2.3): NaN
    /// makes every comparison (`> 0.5`, `< 0.5`, `== 0.5`) silently false
    /// without panicking, corrupting thresholding logic with no test catching
    /// it. NaN clamps to 0.5 (a neutral midpoint); +/-infinity clamp to 1.0/0.0.
    pub fn clamp_probability(p: f32) -> f32 {
        if p.is_nan() {
            0.5
        } else {
            p.clamp(0.0, 1.0)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamp_rejects_nan() {
        assert!(!Score::clamp_probability(f32::NAN).is_nan());
    }

    #[test]
    fn clamp_rejects_positive_infinity() {
        assert_eq!(Score::clamp_probability(f32::INFINITY), 1.0);
    }

    #[test]
    fn clamp_rejects_negative_infinity() {
        assert_eq!(Score::clamp_probability(f32::NEG_INFINITY), 0.0);
    }

    #[test]
    fn clamp_passes_through_valid_values() {
        assert_eq!(Score::clamp_probability(0.42), 0.42);
    }

    #[test]
    fn clamp_bounds_out_of_range_values() {
        assert_eq!(Score::clamp_probability(1.5), 1.0);
        assert_eq!(Score::clamp_probability(-0.5), 0.0);
    }

    #[test]
    fn new_constructs_with_clamped_probability() {
        let s = Score::new(
            "vocabulary".into(),
            crate::backend::SignalFamily::Vocabulary,
            f32::NAN,
            ConfidenceTier::Medium,
            VoteStrength::Suspicious,
            vec![],
        );
        assert!(!s.human_probability.is_nan());
    }

    #[test]
    fn sorting_scores_by_probability_uses_total_cmp() {
        let mut scores = vec![0.9_f32, f32::NAN, 0.1, 0.5];
        scores.sort_by(f32::total_cmp);
        assert_eq!(scores[0], 0.1);
        assert_eq!(scores[1], 0.5);
        assert_eq!(scores[2], 0.9);
        assert!(scores[3].is_nan());
    }
}
