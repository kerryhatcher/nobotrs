#![cfg(feature = "models-detectorscope")]

use nobotrs::{
    backend::ScoreOutcome,
    config::Settings,
    models::{ModelEvidence, ModelRegistry},
    pipeline::{Engine, Report},
};

fn evidence(report: &Report) -> &ModelEvidence {
    assert!(report.complete, "{:?}", report.incomplete_reasons);
    let outcome = &report
        .backends
        .iter()
        .find(|result| result.backend == "detectorscope")
        .unwrap()
        .outcome;
    let ScoreOutcome::Scored(score) = outcome else {
        panic!("expected a DetectorScope score, got {outcome:?}");
    };
    score.model_evidence.as_ref().unwrap()
}

#[test]
#[ignore = "requires the staged DetectorScope artifacts and worker environment"]
fn detector_scope_preserves_signed_evidence_and_reports_token_clipping() {
    let settings = Settings {
        language: Some("en".into()),
        models: vec!["detectorscope".into()],
        models_dir: Some(std::env::var_os("NOBOTRS_MODELS_DIR").unwrap().into()),
        timeout_ms: 180_000,
        ..Settings::default()
    };
    let registry = ModelRegistry::resolve(&settings).unwrap();
    let engine = Engine::new().unwrap();
    let unicode = "The group called it “café day” — the volunteers agreed to move the ﬁrst event outside. The office sent a notice and kept the old date on the agenda.";
    let report = engine
        .analyze_with_models(unicode.into(), false, "unicode.txt", &settings, &registry)
        .unwrap();
    let observed = evidence(&report);
    assert!(!observed.truncated);
    assert_eq!(observed.excerpt_coverage, Some(1.0));
    let (logit, negative_ids) = match (observed.device.as_str(), observed.precision.as_str()) {
        ("cpu", "float32") => (0.5247440934, [60396, 41667, 29327, 23769, 64665]),
        ("cuda", "bfloat16") => (0.5256628990, [41667, 60396, 29327, 23769, 64665]),
        variant => panic!("no reference for {variant:?}"),
    };
    assert!((observed.raw_output - logit).abs() < 1e-5);
    let features = observed.detectorscope.as_ref().unwrap();
    assert!((features.bias - 0.6096460819).abs() < 1e-6);
    assert_eq!(features.active_features, 10);
    assert_eq!(features.omitted_features, 4);
    assert_eq!(features.top_features.len(), 6);
    assert_eq!(features.top_features[0].id, 54983);
    assert!(features.top_features[0].contribution > 0.0);
    for (feature, id) in features.top_features[1..].iter().zip(negative_ids) {
        assert_eq!(feature.id, id);
        assert!(feature.contribution < 0.0);
    }
    let displayed_sum: f64 = features.top_features.iter().map(|f| f.contribution).sum();
    assert!(
        (features.bias + displayed_sum + features.remainder - observed.raw_output).abs() < 1e-6
    );
    let mut highlight_count = 0;
    for feature in &features.top_features {
        for highlight in &feature.highlights {
            let source: String = highlight
                .source_ranges
                .iter()
                .map(|range| &unicode[range.clone()])
                .collect();
            assert_eq!(source, highlight.text);
            highlight_count += 1;
        }
    }
    assert!(highlight_count > 0);

    let boundary = "Test world. ".repeat(340) + "Test world.";
    let report = engine
        .analyze_with_models(boundary, false, "boundary.txt", &settings, &registry)
        .unwrap();
    let exact = evidence(&report);
    assert_eq!(exact.excerpt_tokens, 1024);
    assert!(!exact.truncated);

    let long = "Test world. ".repeat(799) + "Test world.";
    let report = engine
        .analyze_with_models(long, false, "long.txt", &settings, &registry)
        .unwrap();
    let observed = evidence(&report);
    assert_eq!(observed.excerpt_tokens, 1024);
    assert!(observed.truncated);
    assert!((observed.raw_output - exact.raw_output).abs() < 1e-5);
    let retained = observed.excerpt_coverage.unwrap();
    assert!((0.42..0.44).contains(&retained), "retained {retained}");
}
