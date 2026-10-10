use nobotrs::{
    aggregate::{aggregate, Verdict},
    backend::{DetectorBackend, ScoreOutcome, SignalFamily},
    backends::{punctuation::Punctuation, vocabulary::Vocabulary},
    config::Settings,
    deadline::Deadline,
    dictionary::{Dictionary, DictionaryEntry, EntryKind, MatchType},
    document::Document,
    pipeline::Engine,
    score::{ConfidenceTier, Score, VoteStrength},
};
use std::time::Duration;
fn run(raw: &str, markdown: bool) -> nobotrs::pipeline::Report {
    Engine::new()
        .unwrap()
        .analyze(raw.into(), markdown, "fixture.md", &Settings::default())
        .unwrap()
}
fn findings(report: &nobotrs::pipeline::Report) -> Vec<&nobotrs::score::Evidence> {
    report
        .backends
        .iter()
        .flat_map(|b| match &b.outcome {
            ScoreOutcome::Scored(s) | ScoreOutcome::Incomplete { score: s, .. } => {
                s.evidence.iter().collect::<Vec<_>>()
            }
            _ => vec![],
        })
        .collect()
}
#[test]
fn fences_frontmatter_and_stats_use_prose_only() {
    let text = format!(
        "---\nx: delve\n---\n````rust\n{} — — — — — —\n```\ncode\n````\nThe cat sat.\n",
        "word ".repeat(160)
    );
    let r = run(&text, true);
    assert_eq!(r.prose_words, 3);
    assert!(findings(&r).is_empty());
    assert!(r
        .backends
        .iter()
        .filter(|b| matches!(
            b.family,
            SignalFamily::Burstiness
                | SignalFamily::Readability
                | SignalFamily::Compression
                | SignalFamily::LexicalDiversity
        ))
        .all(|b| matches!(b.outcome, ScoreOutcome::Abstained { .. })));
    assert_eq!(
        run("---\na: 1\n---\n```\nonly code\n```", true).verdict,
        Verdict::Inconclusive
    );
}
#[test]
fn markdown_normalization_keeps_semantic_boundaries() {
    for text in [
        "experts agree",
        "experts\nagree",
        "experts *agree*",
        "experts [agree](https://example.com)",
    ] {
        assert!(
            findings(&run(text, true))
                .iter()
                .any(|e| e.rule_id == "experts-agree"),
            "{text}"
        );
    }
    for text in [
        "experts\n\nagree",
        "- experts\n- agree",
        "experts `code` agree",
        "experts | agree\n---|---\none|two",
    ] {
        assert!(
            !findings(&run(text, true))
                .iter()
                .any(|e| e.rule_id == "experts-agree"),
            "{text}"
        );
    }
    assert_eq!(
        Document::from_stdin_text("del*ve*".into(), true)
            .prose
            .trim(),
        "delve"
    );
    assert_eq!(
        Document::from_stdin_text("del<!-- comment -->ve".into(), true)
            .prose
            .trim(),
        "delve"
    );
    assert_eq!(
        Document::from_stdin_text("del`code`ve".into(), true)
            .prose
            .trim(),
        "del\nve"
    );
}
#[test]
fn entity_and_unicode_source_mapping() {
    for dash in ["—", "&mdash;", "&#8212;"] {
        let raw = format!("é\r\n\r\nx {dash} x {dash} x {dash} x");
        let r = run(&raw, true);
        let f = findings(&r);
        assert_eq!(f.len(), 3, "{dash}");
        assert_eq!((f[0].line, f[0].column), (3, 3));
        assert_eq!(&raw[f[0].raw_offset.clone()], dash);
    }
    assert!(!Document::from_stdin_text("&mdash;".into(), false)
        .prose
        .contains('—'));
    let r = run("é\r\nexperts *agree*", true);
    let f = findings(&r);
    let e = f.iter().find(|e| e.rule_id == "experts-agree").unwrap();
    assert_eq!((e.line, e.column), (2, 1));
    assert!(e.source_ranges.len() > 1);
}
#[test]
fn welsh_is_not_accepted_as_english() {
    let raw="Mae'r llyfr hwn yn disgrifio hanes y dref a bywyd y bobl sy'n byw yno. Rydym yn gweithio gyda'n gilydd i wella'r ysgol a helpu'r plant. ".repeat(10);
    let r = run(&raw, false);
    assert_eq!(r.language.applicability, "unknown");
    for b in r.backends.iter().filter(|b| {
        matches!(
            b.family,
            SignalFamily::Readability | SignalFamily::LexicalDiversity
        )
    }) {
        assert!(matches!(b.outcome, ScoreOutcome::Abstained { .. }));
    }
    let r = Engine::new()
        .unwrap()
        .analyze(
            raw,
            false,
            "welsh.txt",
            &Settings {
                language: Some("cy".into()),
                ..Settings::default()
            },
        )
        .unwrap();
    assert_eq!(r.language.applicability, "unsupported");
}
fn entry(
    id: &str,
    pattern: &str,
    regex: bool,
    whole_word: bool,
    sensitive: bool,
) -> DictionaryEntry {
    DictionaryEntry {
        id: id.into(),
        kind: EntryKind::Phrase,
        match_type: if regex {
            MatchType::Regex
        } else {
            MatchType::Exact
        },
        pattern: pattern.into(),
        variants: vec![],
        case_sensitive: sensitive,
        whole_word,
        family: SignalFamily::Vocabulary,
        category: "test".into(),
        suggested_replacements: vec![],
        model_era: vec![],
        source: None,
        notes: None,
    }
}
fn vocab(entries: Vec<DictionaryEntry>, text: &str) -> Score {
    let b = Vocabulary::new(Dictionary {
        schema_version: "1.0.0".into(),
        dictionary_version: "test".into(),
        entries,
    })
    .unwrap();
    match b.score(
        &Document::from_stdin_text(text.into(), false),
        Deadline::new(Duration::from_secs(2)),
    ) {
        ScoreOutcome::Scored(s) => s,
        o => panic!("{o:?}"),
    }
}
#[test]
fn overlap_boundary_case_and_order_regressions() {
    for a in [false, true] {
        for b in [false, true] {
            for reverse in [false, true] {
                let mut entries = vec![
                    entry("short", "abc", a, false, false),
                    entry("long", "bcdefghi", b, false, false),
                ];
                if reverse {
                    entries.reverse();
                }
                let s = vocab(entries, "abcdefghi");
                assert_eq!(s.evidence.len(), 1);
                assert_eq!(s.evidence[0].rule_id, "long");
                assert_eq!(s.candidates.len(), 2);
            }
        }
    }
    let s = vocab(
        vec![
            entry("long", "foo bar", false, true, false),
            entry("short", "foo", false, true, false),
        ],
        "foo barx",
    );
    assert_eq!(s.evidence[0].rule_id, "short");
    assert!(vocab(
        vec![entry("caps", "ONLYCAPS", false, true, true)],
        "onlycaps"
    )
    .evidence
    .is_empty());
    assert_eq!(
        vocab(
            vec![entry("caps", "ONLYCAPS", false, true, true)],
            "ONLYCAPS"
        )
        .evidence
        .len(),
        1
    );
    let s = vocab(
        vec![
            entry("z", "abc", false, false, false),
            entry("a", "abc", true, false, false),
        ],
        "abc",
    );
    assert_eq!(s.evidence[0].rule_id, "a");
}
#[test]
fn suppression_reselects_embedded_overlapping_rules() {
    let engine = Engine::new().unwrap();
    for limit in [0, 1, 200] {
        let settings = Settings {
            ignore_rules: vec!["embark-on-a-journey".into()],
            display_limit: limit,
            ..Settings::default()
        };
        let r = engine
            .analyze(
                "embark on a journey, embark on a journey".into(),
                false,
                "test.txt",
                &settings,
            )
            .unwrap();
        assert_eq!(r.effective_finding_count, 2);
        assert_eq!(
            r.families
                .iter()
                .find(|f| f.family == SignalFamily::Vocabulary)
                .unwrap()
                .vote,
            VoteStrength::Suspicious
        );
        assert_eq!(r.exit_code(true), 1);
        if limit > 0 {
            assert_eq!(findings(&r)[0].rule_id, "embark");
        }
    }
    for ids in [vec!["embark"], vec!["embark", "embark-on-a-journey"]] {
        let r = engine
            .analyze(
                "embark on a journey".into(),
                false,
                "test.txt",
                &Settings {
                    ignore_rules: ids.iter().map(|s| s.to_string()).collect(),
                    ..Settings::default()
                },
            )
            .unwrap();
        assert_eq!(
            r.effective_finding_count,
            if ids.len() == 2 { 0 } else { 1 }
        );
    }
    let raw="<!-- nobotrs-ignore-next-line embark-on-a-journey -->\nembark on a journey\n\nembark on a journey";
    let r = run(raw, true);
    assert_eq!(
        findings(&r)
            .iter()
            .map(|e| e.rule_id.as_str())
            .collect::<Vec<_>>(),
        ["embark", "embark-on-a-journey"]
    );
    let raw = "```\n<!-- nobotrs-ignore-file embark -->\n```\nembark";
    assert_eq!(run(raw, true).effective_finding_count, 1);
}
#[test]
fn budgets_and_display_are_distinct() {
    let engine = Engine::new().unwrap();
    for settings in [
        Settings {
            timeout_ms: 0,
            ..Settings::default()
        },
        Settings {
            max_candidates: 1,
            ..Settings::default()
        },
    ] {
        let r = engine
            .analyze(
                "delve leverage nuanced multifaceted".into(),
                false,
                "test.txt",
                &settings,
            )
            .unwrap();
        assert!(!r.complete);
        assert_eq!(r.exit_code(true), 2);
        assert!(r.analyzed_coverage < 1.0);
    }
    let r = engine
        .analyze(
            "delve leverage — — — — — —".into(),
            false,
            "test.txt",
            &Settings {
                display_limit: 0,
                ..Settings::default()
            },
        )
        .unwrap();
    assert!(r.complete);
    assert_eq!(r.verdict, Verdict::Flagged);
    assert_eq!(r.exit_code(false), 1);
    assert!(r.omitted_findings > 0);
    assert!(findings(&r).is_empty());
    let doc = Document::from_stdin_text("— — —".into(), false);
    assert!(matches!(
        Punctuation.score(&doc, Deadline::new(Duration::ZERO)),
        ScoreOutcome::Failed(_)
    ));
}
fn scored(backend: &str, family: SignalFamily, vote: VoteStrength) -> (SignalFamily, ScoreOutcome) {
    (
        family,
        ScoreOutcome::Scored(Score::new(
            backend.into(),
            family,
            ConfidenceTier::Low,
            vote,
            vec![],
        )),
    )
}
#[test]
fn family_participation_and_failures_are_honest() {
    let r = aggregate(
        vec![
            scored("one", SignalFamily::Readability, VoteStrength::None),
            scored("two", SignalFamily::Compression, VoteStrength::None),
        ],
        2,
    )
    .unwrap();
    assert_eq!(r.verdict, Verdict::Inconclusive);
    let r = aggregate(
        vec![
            scored("one", SignalFamily::Vocabulary, VoteStrength::Strong),
            scored("two", SignalFamily::Vocabulary, VoteStrength::Strong),
        ],
        2,
    )
    .unwrap();
    assert_eq!(r.votes_cast, 1);
    assert_eq!(r.scores.len(), 2);
    assert_eq!(r.verdict, Verdict::Inconclusive);
    assert!(aggregate(
        vec![
            scored("same", SignalFamily::Vocabulary, VoteStrength::None),
            scored("same", SignalFamily::Vocabulary, VoteStrength::None)
        ],
        2
    )
    .is_err());
    assert!(aggregate(vec![], 0).is_err());
    let mut mismatch = scored("one", SignalFamily::Vocabulary, VoteStrength::None);
    mismatch.0 = SignalFamily::Punctuation;
    assert!(aggregate(vec![mismatch], 2).is_err());
    let r = aggregate(
        vec![
            scored("one", SignalFamily::Vocabulary, VoteStrength::Strong),
            scored("two", SignalFamily::Punctuation, VoteStrength::Strong),
            (
                SignalFamily::Compression,
                ScoreOutcome::Failed(nobotrs::error::Error::Timeout),
            ),
        ],
        2,
    )
    .unwrap();
    assert_eq!(r.verdict, Verdict::Flagged);
    assert_eq!(r.warnings.len(), 1);
}
#[test]
fn long_single_line_unicode_locations_are_indexed() {
    let raw = format!(
        "{}delve {}leverage",
        "é ".repeat(50_000),
        "é ".repeat(50_000)
    );
    let r = run(&raw, false);
    let f = findings(&r);
    assert_eq!(f.len(), 2);
    assert_eq!(f[0].column, 100_001);
    assert_eq!(f[1].column, 200_007);
}

#[test]
fn scopes_path_policy_and_document_metrics_remain_distinct() {
    let engine = Engine::new().unwrap();
    let mut settings = Settings::default();
    settings
        .path_ignores
        .insert("docs/*".into(), vec!["embark-on-a-journey".into()]);
    let r = engine
        .analyze(
            "embark on a journey".into(),
            false,
            "docs/example.txt",
            &settings,
        )
        .unwrap();
    assert_eq!(findings(&r)[0].rule_id, "embark");
    let r = engine
        .analyze(
            "embark on a journey".into(),
            false,
            "other/example.txt",
            &settings,
        )
        .unwrap();
    assert_eq!(findings(&r)[0].rule_id, "embark-on-a-journey");
    let r=run("We embark on a journey <!-- nobotrs-ignore-block embark-on-a-journey --> today.\n\nWe embark on a journey.",true);
    assert_eq!(
        findings(&r)
            .iter()
            .map(|e| e.rule_id.as_str())
            .collect::<Vec<_>>(),
        ["embark", "embark-on-a-journey"]
    );
    let r = run(
        "<!-- nobotrs-ignore-next-line punctuation.em-dash-density -->\nx — — — — —\n\nx — x",
        true,
    );
    assert_eq!(
        r.families
            .iter()
            .find(|f| f.family == SignalFamily::Punctuation)
            .unwrap()
            .vote,
        VoteStrength::None
    );
    let b = r
        .backends
        .iter()
        .find(|b| b.backend == "punctuation")
        .unwrap();
    if let ScoreOutcome::Scored(s) = &b.outcome {
        assert_eq!(s.metrics["em_dash_count"].value, 6.0);
        assert_eq!(s.metrics["effective_em_dash_count"].value, 1.0);
    } else {
        panic!("punctuation should score");
    }
}
#[test]
fn syllables_and_shared_sentence_counts_are_punctuation_invariant() {
    let engine = Engine::new().unwrap();
    for word in ["time", "time.", "\"time\""] {
        let r = engine
            .analyze(
                format!("{word} ").repeat(160),
                false,
                "sample.txt",
                &Settings {
                    language: Some("en".into()),
                    ..Settings::default()
                },
            )
            .unwrap();
        let b = r
            .backends
            .iter()
            .find(|b| b.backend == "readability")
            .unwrap();
        if let ScoreOutcome::Scored(s) = &b.outcome {
            let grade = s.metrics["flesch_kincaid_grade"].value;
            let expected = 0.39 * 160.0 / r.sentence_count as f64 + 11.8 - 15.59;
            assert!((grade - expected).abs() < 1e-8);
        } else {
            panic!("English long prose should score");
        }
    }
    let d = Document::from_stdin_text(
        "Dr. Smith paid 3.14 dollars... Really?! Yes.\u{2003}Done".into(),
        false,
    );
    assert_eq!(d.sentences.len(), 4);
}
#[test]
fn named_failures_cannot_duplicate_backend_participation() {
    use nobotrs::aggregate::{aggregate_backends, BackendOutcome};
    let outcomes = (0..2)
        .map(|_| BackendOutcome {
            backend: "duplicate".into(),
            family: SignalFamily::Vocabulary,
            outcome: ScoreOutcome::Failed(nobotrs::error::Error::Timeout),
        })
        .collect();
    assert!(aggregate_backends(outcomes, 2).is_err());
}

#[test]
fn overlap_chain_and_invalid_dictionary_are_regressions() {
    let s = vocab(
        vec![
            entry("left", "abcd", false, false, false),
            entry("middle", "defghi", false, false, false),
            entry("right", "ijkl", true, false, false),
        ],
        "abcdefghijkl",
    );
    assert_eq!(s.evidence.len(), 1);
    assert_eq!(s.evidence[0].rule_id, "middle");
    assert_eq!(s.candidates.len(), 3);
    for entries in [
        vec![
            entry("same", "x", false, true, false),
            entry("same", "y", false, true, false),
        ],
        vec![entry("empty", "", false, true, false)],
    ] {
        assert!(Vocabulary::new(Dictionary {
            schema_version: "1.0.0".into(),
            dictionary_version: "test".into(),
            entries
        })
        .is_err());
    }
}
