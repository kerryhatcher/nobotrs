//! Optional within-document classifier diagnostics. No automatic editing recommendations.
use crate::{
    document::Document,
    models::{ModelEvidence, WindowEvidence},
};
use serde::Serialize;
use std::ops::Range;
pub const LABEL: &str =
    "Where local classifiers react most. Not a Google signal and not evidence of authorship.";
pub const RANKING_POLICY: &str = "within-doc-z-v1";
#[derive(Debug, Clone, Serialize)]
pub struct ModelRank {
    pub backend: String,
    pub raw_output: f64,
    pub z: f64,
    pub rank: usize,
}
#[derive(Debug, Clone, Serialize)]
pub struct HotspotFeature {
    pub feature_id: usize,
    pub description: String,
    pub direction: i8,
    pub max_activation: f64,
    pub guidance_id: Option<String>,
}
#[derive(Debug, Clone, Serialize)]
pub struct Hotspot {
    pub rank: usize,
    pub heading: Option<String>,
    pub prose: Range<usize>,
    pub source_ranges: Vec<Range<usize>>,
    pub units: Range<usize>,
    pub line: u32,
    pub end_line: u32,
    pub body_tokens: usize,
    pub mean_z: f64,
    pub per_model: Vec<ModelRank>,
    pub agreement: usize,
    pub features: Vec<HotspotFeature>,
}
#[derive(Debug, Clone, Serialize)]
pub struct DiagnosticProvenance {
    pub backend: String,
    pub model_revision: String,
    pub tokenizer_revision: String,
    pub code_revision: Option<String>,
    pub preprocessing_revision: String,
    pub runtime: String,
    pub device: String,
    pub precision: String,
    pub token_limit: usize,
    pub token_coverage: Option<f64>,
    pub coverage_gaps: Vec<Range<usize>>,
    pub licenses: serde_json::Value,
}
#[derive(Debug, Clone, Serialize)]
pub struct HotspotReport {
    pub label: &'static str,
    pub ranking_policy: &'static str,
    pub validated: bool,
    pub reason: Option<String>,
    pub hotspots: Vec<Hotspot>,
    pub provenance: Vec<DiagnosticProvenance>,
    pub guidance_version: String,
    pub minimum_body_tokens: usize,
}
fn overlap(a: &Range<usize>, b: &Range<usize>) -> usize {
    a.end.min(b.end).saturating_sub(a.start.max(b.start))
}
fn validation() -> bool {
    let v: serde_json::Value =
        serde_json::from_str(include_str!("../guidance/hotspot-validation.json"))
            .expect("hotspot validation JSON");
    // The measured, blinded utility gate is distinct from classifier accuracy and edit overlap.
    v["validated"] == true
        && v["record"].as_str().is_some_and(|s| !s.is_empty())
        && v["blinded_editor_utility_passed"] == true
}
struct Ranked<'a> {
    model: &'a ModelEvidence,
    windows: Vec<(&'a WindowEvidence, f64, usize)>,
}
pub fn rank(doc: &Document, evidence: &[&ModelEvidence]) -> HotspotReport {
    let mut report = HotspotReport {
        label: LABEL,
        ranking_policy: RANKING_POLICY,
        validated: validation(),
        reason: None,
        hotspots: vec![],
        provenance: evidence
            .iter()
            .map(|e| DiagnosticProvenance {
                backend: e.backend.clone(),
                model_revision: e.model_revision.clone(),
                tokenizer_revision: e.tokenizer_revision.clone(),
                code_revision: e.code_revision.clone(),
                preprocessing_revision: e.preprocessing_revision.clone(),
                runtime: e.runtime.clone(),
                device: e.device.clone(),
                precision: e.precision.clone(),
                token_limit: e.token_limit,
                token_coverage: e.token_coverage,
                coverage_gaps: e.coverage_gaps.clone(),
                licenses: crate::models::manifest(&e.backend)
                    .map_or(serde_json::Value::Null, |m| m.licenses.clone()),
            })
            .collect(),
        guidance_version: crate::guidance::Guidance::embedded()
            .guidance_version
            .clone(),
        minimum_body_tokens: 128,
    };
    let mut ranked = Vec::new();
    for model in evidence {
        // Partial documents do not provide a comparable within-document ranking.
        if model.token_coverage != Some(1.0) || !model.coverage_gaps.is_empty() {
            continue;
        }
        let mut eligible: Vec<_> = model
            .windows
            .iter()
            .filter(|w| {
                w.status == "scored"
                    && w.body_tokens >= 128
                    && w.raw_output.is_some_and(f64::is_finite)
            })
            .collect();
        if eligible.len() < 2 {
            continue;
        }
        let mean =
            eligible.iter().map(|w| w.raw_output.unwrap()).sum::<f64>() / eligible.len() as f64;
        let sd = (eligible
            .iter()
            .map(|w| (w.raw_output.unwrap() - mean).powi(2))
            .sum::<f64>()
            / eligible.len() as f64)
            .sqrt();
        if sd <= f64::EPSILON {
            continue;
        }
        eligible.sort_by(|a, b| {
            b.raw_output
                .unwrap()
                .total_cmp(&a.raw_output.unwrap())
                .then(a.prose.start.cmp(&b.prose.start))
        });
        let windows = eligible
            .into_iter()
            .enumerate()
            .map(|(i, w)| (w, (w.raw_output.unwrap() - mean) / sd, i + 1))
            .collect();
        ranked.push(Ranked { model, windows });
    }
    let Some(base) = ranked.first() else {
        if evidence.is_empty() {
            report.reason =
                Some("no completed model evidence; inspect skipped and incomplete checks".into());
            return report;
        }
        report.reason = Some(
            if evidence
                .iter()
                .flat_map(|e| &e.windows)
                .all(|w| w.body_tokens < 128)
            {
                "no window reaches 128 tokens"
            } else {
                "need at least two distinct eligible windows in a complete model run"
            }
            .into(),
        );
        return report;
    };
    // Reference windows form one source partition. Other tokenizers join by greatest unit
    // overlap, breaking ties by byte overlap, with one score per model per reference window.
    for (reference, _, _) in &base.windows {
        let mut per_model = Vec::new();
        let mut features = Vec::new();
        for model in &ranked {
            let best = model
                .windows
                .iter()
                .filter(|(w, _, _)| {
                    overlap(&reference.units, &w.units) > 0
                        && overlap(&reference.prose, &w.prose) > 0
                })
                .max_by_key(|(w, _, _)| {
                    (
                        overlap(&reference.units, &w.units),
                        overlap(&reference.prose, &w.prose),
                        std::cmp::Reverse(w.index),
                    )
                });
            let Some((w, z, rank)) = best else {
                continue;
            };
            per_model.push(ModelRank {
                backend: model.model.backend.clone(),
                raw_output: w.raw_output.unwrap(),
                z: *z,
                rank: *rank,
            });
            if let Some(ds) = &w.detectorscope {
                for f in &ds.top_features {
                    let max_activation = f
                        .highlights
                        .iter()
                        .map(|h| h.activation)
                        .filter(|v| v.is_finite())
                        .fold(0.0, f64::max);
                    features.push(HotspotFeature {
                        feature_id: f.id,
                        description: f.description.clone(),
                        direction: if f.contribution > 0.0 {
                            1
                        } else if f.contribution < 0.0 {
                            -1
                        } else {
                            0
                        },
                        max_activation,
                        guidance_id: crate::guidance::detectorscope_guidance(f.id)
                            .map(|g| g.id.clone()),
                    });
                }
            }
        }
        if per_model.is_empty() {
            continue;
        }
        let mean_z = per_model.iter().map(|m| m.z).sum::<f64>() / per_model.len() as f64;
        let line = reference
            .source_ranges
            .first()
            .map_or(1, |r| doc.location(r.start).0);
        let end_line = reference
            .source_ranges
            .last()
            .map_or(line, |r| doc.location(r.end).0);
        report.hotspots.push(Hotspot {
            rank: 0,
            heading: reference.heading.clone(),
            prose: reference.prose.clone(),
            source_ranges: reference.source_ranges.clone(),
            units: reference.units.clone(),
            line,
            end_line,
            body_tokens: reference.body_tokens,
            mean_z,
            agreement: per_model.iter().filter(|m| m.rank <= 3).count(),
            per_model,
            features,
        });
    }
    report.hotspots.sort_by(|a, b| {
        b.mean_z
            .total_cmp(&a.mean_z)
            .then(a.prose.start.cmp(&b.prose.start))
    });
    report.hotspots.truncate(5);
    for (i, h) in report.hotspots.iter_mut().enumerate() {
        h.rank = i + 1;
    }
    report
}

#[cfg(test)]
mod tests {
    use super::*;
    fn model(name: &str, values: &[f64]) -> ModelEvidence {
        ModelEvidence {
            backend: name.into(),
            model_revision: "test".into(),
            tokenizer_revision: "test".into(),
            code_revision: None,
            runtime: "synthetic".into(),
            device: "cpu".into(),
            precision: "f64".into(),
            preprocessing_revision: "test".into(),
            raw_output: 0.0,
            raw_units: "logit".into(),
            threshold: None,
            threshold_source: None,
            prepared_bytes: 40,
            prepared_words: 20,
            excerpt_bytes: 10,
            excerpt_tokens: 10,
            token_limit: 512,
            truncated: true,
            planned_coverage: Some(0.25),
            execution_coverage: Some(0.25),
            excerpt_coverage: Some(0.25),
            elapsed_ms: 0.0,
            detectorscope: None,
            packing_policy: Some("section-packed-v1".into()),
            aggregation_policy: Some("token-weighted-mean-v1".into()),
            full_coverage_output: Some(0.0),
            token_coverage: Some(1.0),
            coverage_gaps: vec![],
            windows: values
                .iter()
                .enumerate()
                .map(|(i, &v)| WindowEvidence {
                    index: i,
                    prose: i * 10..(i + 1) * 10,
                    source_ranges: std::iter::once(i * 10..(i + 1) * 10).collect(),
                    units: i..i + 1,
                    heading: None,
                    body_tokens: 128,
                    status: "scored".into(),
                    error: None,
                    raw_output: Some(v),
                    insufficient_context: false,
                    detectorscope: None,
                })
                .collect(),
        }
    }
    fn doc() -> Document {
        Document::from_stdin_text(
            "One line. Two lines. Three lines. Four lines.".into(),
            false,
        )
    }
    #[test]
    fn ranks_by_within_document_z_and_exposes_disagreement() {
        let a = model("desklib", &[4.0, 3.0, 2.0, 1.0]);
        let b = model("conpara", &[0.0, 1.0, 2.0, 3.0]);
        let r = rank(&doc(), &[&a]);
        assert_eq!(r.hotspots[0].prose, 0..10);
        assert_eq!(r.hotspots[0].rank, 1);
        let r = rank(&doc(), &[&a, &b]);
        let first = r.hotspots.iter().find(|h| h.prose.start == 0).unwrap();
        assert_eq!(first.agreement, 1);
        assert_eq!(first.per_model[0].rank, 1);
        assert_eq!(first.per_model[1].rank, 4);
        assert_eq!(r.label, LABEL);
        assert!(!r.validated);
        assert_eq!(r.ranking_policy, "within-doc-z-v1");
        assert!(!serde_json::to_string(&r.hotspots)
            .unwrap()
            .contains("contribution"));
    }
    #[test]
    fn too_short_partial_or_constant_windows_are_not_ranked() {
        let mut a = model("desklib", &[1.0, 2.0]);
        for w in &mut a.windows {
            w.body_tokens = 127;
            w.insufficient_context = true;
        }
        let r = rank(&doc(), &[&a]);
        assert!(r.hotspots.is_empty());
        assert_eq!(r.reason.as_deref(), Some("no window reaches 128 tokens"));
        let a = model("desklib", &[1.0, 1.0]);
        assert!(rank(&doc(), &[&a]).hotspots.is_empty());
        let mut a = model("desklib", &[1.0, 2.0]);
        a.token_coverage = Some(0.5);
        assert!(rank(&doc(), &[&a]).hotspots.is_empty());
    }
    #[test]
    fn unequal_tokenizer_windows_join_by_units() {
        let a = model("desklib", &[1.0, 2.0, 3.0, 4.0]);
        let mut b = model("conpara", &[5.0, 6.0]);
        b.windows[0].units = 0..2;
        b.windows[0].prose = 0..20;
        b.windows[1].units = 2..4;
        b.windows[1].prose = 20..40;
        let r = rank(&doc(), &[&a, &b]);
        assert_eq!(r.hotspots.len(), 4);
        assert!(r.hotspots.iter().all(|h| h.per_model.len() == 2));
    }
}
