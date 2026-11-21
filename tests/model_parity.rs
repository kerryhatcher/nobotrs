#![cfg(feature = "models-encoders")]

use nobotrs::{
    backend::{ScoreOutcome, SignalFamily},
    config::Settings,
    models::ModelRegistry,
    pipeline::Engine,
};
use serde_json::Value;

fn fixture() -> Value {
    serde_json::from_str(include_str!("fixtures/models/encoder-reference.json")).unwrap()
}

#[test]
fn native_encoders_match_pinned_python_reference_when_enabled() {
    let Ok(models_dir) = std::env::var("NOBOTRS_MODELS_DIR") else {
        eprintln!(
            "skipping native encoder parity; set NOBOTRS_MODEL_PARITY=1 and NOBOTRS_MODELS_DIR"
        );
        return;
    };
    if std::env::var_os("NOBOTRS_MODEL_PARITY").is_none() {
        eprintln!("skipping native encoder parity; set NOBOTRS_MODEL_PARITY=1");
        return;
    }
    let fixture = fixture();
    let tolerance = fixture["tolerance"]["absolute_score"]
        .as_f64()
        .unwrap_or(1e-3);
    let settings = Settings {
        language: Some("en".into()),
        models: vec!["desklib".into(), "conpara".into()],
        models_dir: Some(models_dir.into()),
        timeout_ms: 300_000,
        ..Default::default()
    };
    let registry = ModelRegistry::resolve(&settings).unwrap();
    let engine = Engine::new().unwrap();
    for case in fixture["cases"].as_array().unwrap() {
        let text = case["text"].as_str().unwrap();
        let report = engine
            .analyze_with_models(text.into(), false, "fixture.txt", &settings, &registry)
            .unwrap();
        assert!(
            report
                .families
                .iter()
                .all(|family| family.family != SignalFamily::Model),
            "model family must never participate in heuristic quorum"
        );
        assert!(!report
            .settings
            .enabled_backends
            .iter()
            .any(|name| matches!(name.as_str(), "desklib" | "conpara" | "detectorscope")));
        for backend in ["desklib", "conpara"] {
            let expected = &case[backend];
            let outcome = report
                .backends
                .iter()
                .find(|item| item.backend == backend)
                .unwrap();
            if text.split_whitespace().count() < 25 {
                assert!(
                    matches!(outcome.outcome, ScoreOutcome::Abstained { .. }),
                    "{backend} must abstain on too-short fixture"
                );
                continue;
            }
            let ScoreOutcome::Scored(score) = &outcome.outcome else {
                panic!("{backend} did not score: {:?}", outcome.outcome);
            };
            let evidence = score.model_evidence.as_ref().unwrap();
            let expected_score = expected["score"].as_f64().unwrap();
            assert!(
                (evidence.raw_output - expected_score).abs() <= tolerance,
                "{backend}: rust {} vs python {}",
                evidence.raw_output,
                expected_score
            );
            assert_eq!(evidence.truncated, expected["truncated"].as_bool().unwrap());
            assert_eq!(
                evidence.excerpt_tokens,
                expected["ids"].as_array().unwrap().len()
            );
            assert_eq!(evidence.token_limit, 512);
            let cutoff = evidence.threshold.expect("pinned cutoff");
            let python_cutoff = expected_score >= cutoff;
            let rust_cutoff = evidence.raw_output >= cutoff;
            assert_eq!(
                rust_cutoff, python_cutoff,
                "{backend}: cutoff decision changed at pinned threshold {cutoff}"
            );
            if evidence.truncated {
                assert!(
                    evidence.excerpt_coverage.unwrap_or(1.0) < 1.0,
                    "clipped input must report retained coverage below 100%"
                );
            } else {
                assert_eq!(evidence.excerpt_coverage, Some(1.0));
            }
        }
    }
}
