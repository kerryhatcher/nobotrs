use nobotrs::{
    backend::{DetectorBackend, ScoreOutcome},
    backends::burstiness::Burstiness,
    deadline::Deadline,
    document::Document,
    score::VoteStrength,
};
use std::time::Duration;

fn sentence_text(lengths: &[u64]) -> String {
    lengths
        .iter()
        .map(|length| {
            let words = vec!["word"; *length as usize].join(" ");
            format!("{words}.")
        })
        .collect::<Vec<_>>()
        .join(" ")
}

#[test]
fn pinned_burstiness_reference() {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("../tests/fixtures/burstiness-reference.json")).unwrap();
    let tolerance = fixture["reference"]["comparison_tolerance"]
        .as_f64()
        .unwrap();
    let cases = fixture["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 5);
    let deadline = Deadline::new(Duration::from_secs(5));
    for case in cases {
        let id = case["id"].as_str().unwrap();
        let lengths: Vec<u64> = case["sentence_lengths"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| value.as_u64().unwrap())
            .collect();
        let doc = Document::from_stdin_text(sentence_text(&lengths), false);
        assert_eq!(
            doc.words.len(),
            case["expected_words"].as_u64().unwrap() as usize,
            "{id}: word count"
        );
        assert_eq!(
            doc.sentences.len(),
            case["expected_sentences"].as_u64().unwrap() as usize,
            "{id}: sentence count"
        );
        let outcome = Burstiness.score(&doc, deadline);
        match case["expected_backend_outcome"].as_str().unwrap() {
            "abstained" => assert!(
                matches!(outcome, ScoreOutcome::Abstained { .. }),
                "{id}: expected abstention, got {outcome:?}"
            ),
            "scored" => {
                let ScoreOutcome::Scored(score) = outcome else {
                    panic!("{id}: expected a scored outcome")
                };
                let expected = case["expected_cv"].as_f64().unwrap();
                let actual = score.metrics["sentence_length_cv"].value;
                assert!(
                    (actual - expected).abs() < tolerance,
                    "{id}: burstiness {actual} vs {expected}"
                );
                assert_eq!(
                    score.metrics["sentence_length_cv"].method,
                    "population-stdev/shared-segmentation-v1",
                    "{id}"
                );
                let vote = match case["expected_vote"].as_str().unwrap() {
                    "strong" => VoteStrength::Strong,
                    "suspicious" => VoteStrength::Suspicious,
                    "none" => VoteStrength::None,
                    other => panic!("{id}: unknown vote {other}"),
                };
                assert_eq!(score.vote, vote, "{id}");
            }
            other => panic!("{id}: unknown expected outcome {other}"),
        }
    }
}
