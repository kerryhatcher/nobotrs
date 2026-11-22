use nobotrs::{backend::ScoreOutcome, config::Settings, pipeline::Engine};
#[test]
fn bibb_fixture_offline_baseline_is_pinned() {
    let raw = include_str!("../evaluation/fixtures/bibb-fy27.txt");
    assert_eq!(raw.len(), 2236);
    assert_eq!(raw.chars().count(), 2192);
    let settings = Settings {
        language: Some("en".into()),
        ..Default::default()
    };
    let r = Engine::new()
        .unwrap()
        .analyze(raw.into(), false, "bibb-fy27.txt", &settings)
        .unwrap();
    assert_eq!(serde_json::to_value(r.verdict).unwrap(), "clean");
    assert_eq!(r.sentence_count, 21);
    assert_eq!(r.prose_words, 348);
    assert!(r.complete);
    assert!(!r.backends.iter().any(|b| b.backend == "structure"));
    for (name, expected) in [
        ("sentence_length_cv", 0.9920),
        ("mtld", 199.3117),
        ("flesch_kincaid_grade", 9.2849),
        ("lzma_ratio", 0.6544),
        ("token_entropy", 7.6634),
        ("effective_em_dash_count", 9.0),
    ] {
        let value = r
            .backends
            .iter()
            .filter_map(|b| {
                if let ScoreOutcome::Scored(s) = &b.outcome {
                    s.metrics.get(name)
                } else {
                    None
                }
            })
            .next()
            .unwrap_or_else(|| panic!("missing {name}"));
        assert!(
            (value.value - expected).abs() < 0.00005,
            "{name}: {}",
            value.value
        );
    }
}
