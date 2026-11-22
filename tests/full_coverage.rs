#![cfg(any(feature = "models-encoders", feature = "models-detectorscope"))]
use nobotrs::{
    backend::ScoreOutcome,
    config::{ModelCoverage, Settings},
    models::{ModelEvidence, ModelRegistry},
    pipeline::{Engine, Report},
};
fn settings(model: &str) -> Settings {
    Settings {
        language: Some("en".into()),
        models: vec![model.into()],
        models_dir: Some(
            std::env::var_os("NOBOTRS_MODELS_DIR")
                .expect("staged models directory")
                .into(),
        ),
        timeout_ms: 600_000,
        ..Default::default()
    }
}
fn evidence(report: &Report) -> &ModelEvidence {
    let outcome = &report
        .backends
        .iter()
        .find(|b| b.family == nobotrs::backend::SignalFamily::Model)
        .unwrap()
        .outcome;
    match outcome {
        ScoreOutcome::Scored(s) => s.model_evidence.as_ref().unwrap(),
        ScoreOutcome::Incomplete { score, reason, .. } => panic!(
            "incomplete {reason}: {:?}",
            score.model_evidence.as_ref().map(|e| e
                .windows
                .iter()
                .map(|w| (&w.status, &w.error))
                .collect::<Vec<_>>())
        ),
        _ => panic!("{outcome:?}"),
    }
}
fn compare_opening_and_full(model: &str, raw: &str) {
    let mut settings = settings(model);
    let registry = ModelRegistry::resolve(&settings).unwrap();
    let engine = Engine::new().unwrap();
    let opening = engine
        .analyze_with_models(raw.into(), false, "fixture", &settings, &registry)
        .unwrap();
    let a = evidence(&opening);
    let serialized = serde_json::to_value(a).unwrap();
    for key in [
        "packing_policy",
        "aggregation_policy",
        "windows",
        "token_coverage",
        "full_coverage_output",
        "coverage_gaps",
    ] {
        assert!(serialized.get(key).is_none(), "opening gained {key}");
    }
    settings.model_coverage = ModelCoverage::Full;
    let full = engine
        .analyze_with_models(raw.into(), false, "fixture", &settings, &registry)
        .unwrap();
    let b = evidence(&full);
    assert!((a.raw_output - b.raw_output).abs() < 1e-6);
    assert_eq!(a.excerpt_tokens, b.excerpt_tokens);
    assert_eq!(b.token_coverage, Some(1.0));
    assert!(b.full_coverage_output.is_some());
    assert!(b.coverage_gaps.is_empty());
    assert!(!b.windows.is_empty());
    assert!(b
        .windows
        .iter()
        .all(|w| w.body_tokens > 0 && w.status == "scored" && w.raw_output.unwrap().is_finite()));
    let doc = nobotrs::document::Document::from_stdin_text(raw.into(), false);
    for w in &b.windows {
        assert!(doc.prose.get(w.prose.clone()).is_some());
        for r in &w.source_ranges {
            assert!(raw.get(r.clone()).is_some());
        }
    }
    assert!(b
        .windows
        .windows(2)
        .all(|w| w[0].prose.end <= w[1].prose.start));
}
#[test]
#[ignore = "requires staged model artifacts"]
#[cfg(feature = "models-encoders")]
fn encoder_bibb_full_coverage_preserves_opening() {
    let text = include_str!("../evaluation/fixtures/bibb-fy27.txt");
    for model in ["desklib", "conpara"] {
        compare_opening_and_full(model, text);
    }
}
#[test]
#[ignore = "requires staged model artifacts"]
#[cfg(feature = "models-detectorscope")]
fn detectorscope_bibb_and_long_full_coverage_preserve_opening() {
    let text = include_str!("../evaluation/fixtures/bibb-fy27.txt");
    compare_opening_and_full("detectorscope", text);
    compare_opening_and_full("detectorscope", &[text; 3].join("\n\n"));
}
#[test]
#[ignore = "requires staged model artifacts"]
#[cfg(feature = "models-encoders")]
fn tail_edit_changes_only_full_coverage_and_last_window() {
    let text = include_str!("../evaluation/fixtures/bibb-fy27.txt");
    let before = [text; 3].join("\n\n");
    let after = before.strip_suffix("deferred.").unwrap().to_owned() + "postponed.";
    let mut s = settings("desklib");
    s.model_coverage = ModelCoverage::Full;
    let registry = ModelRegistry::resolve(&s).unwrap();
    let engine = Engine::new().unwrap();
    let a = engine
        .analyze_with_models(before, false, "before", &s, &registry)
        .unwrap();
    let b = engine
        .analyze_with_models(after, false, "after", &s, &registry)
        .unwrap();
    let a = evidence(&a);
    let b = evidence(&b);
    assert_eq!(a.raw_output, b.raw_output);
    assert_eq!(a.windows.len(), b.windows.len());
    for (x, y) in a.windows.iter().zip(&b.windows).take(a.windows.len() - 1) {
        assert_eq!(x.raw_output, y.raw_output);
    }
    assert_ne!(a.full_coverage_output, b.full_coverage_output);
}
