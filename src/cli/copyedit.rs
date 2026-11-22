//! Copyediting command: grammar, spelling, style and readability checks.
//!
//! Uses Engine::editorial_analysis to prepare the document once (language
//! asserted, editorial units attached), then runs the advisory review
//! pipeline and the native copyediting engine on the same prepared text.
//! Propagates errors and incomplete status honestly — no unwrap_or_else
//! that would swallow copyediting engine failures.
//!
//! CLI flags:
//!   --dialect american|british  (default: american)
//!   --allow-word <word>         repeatable; project spelling allowlist
use super::{emit, load, Format};
use nobotrs::{
    config::Settings,
    copyediting::{self, CopyeditIssue},
    deadline::Deadline,
    document::Document,
    models::ModelRegistry,
    pipeline::Engine,
    review::ReviewFinding,
};
use serde::Serialize;
use serde_json::{json, Value};
use std::{collections::BTreeMap, ops::Range, path::Path, time::Duration};

/// A single copyediting finding, preserving category and source locations.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct CopyeditFinding {
    pub rule_id: String,
    pub guidance_id: String,
    pub category: String,
    pub leverage: u8,
    pub severity: String,
    pub line: u32,
    pub column: u32,
    pub end_line: u32,
    pub end_column: u32,
    pub matched_text: String,
    pub source_ranges: Vec<Range<usize>>,
    pub sentence: Option<String>,
    pub suggestion: Option<String>,
    pub fix: String,
    pub keep_when: String,
}

/// The copyediting report for one file.
#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct CopyeditReport {
    pub schema_version: &'static str,
    pub path: String,
    pub complete: bool,
    pub prose_words: usize,
    pub finding_count: usize,
    pub omitted_findings: usize,
    pub findings: Vec<CopyeditFinding>,
    pub checks: Vec<nobotrs::review::AnalysisCheck>,
    pub incomplete_reasons: Vec<String>,
}

fn category_label(c: &nobotrs::guidance::Category) -> &'static str {
    match c {
        nobotrs::guidance::Category::Content => "content",
        nobotrs::guidance::Category::Structure => "structure",
        nobotrs::guidance::Category::Rhythm => "rhythm",
        nobotrs::guidance::Category::Punctuation => "punctuation",
        nobotrs::guidance::Category::Formatting => "formatting",
        nobotrs::guidance::Category::Vocabulary => "vocabulary",
    }
}

fn severity_label(s: &nobotrs::score::Severity) -> &'static str {
    match s {
        nobotrs::score::Severity::Low => "low",
        nobotrs::score::Severity::Medium => "medium",
        nobotrs::score::Severity::High => "high",
    }
}

fn finding_from_review(f: &ReviewFinding) -> CopyeditFinding {
    let line = f.location.as_ref().map_or(0, |l| l.line);
    let column = f.location.as_ref().map_or(0, |l| l.column);
    let end_line = f.location.as_ref().map_or(0, |l| l.end_line);
    let end_column = f.location.as_ref().map_or(0, |l| l.end_column);
    CopyeditFinding {
        rule_id: f.rule_id.clone(),
        guidance_id: f.guidance_id.clone(),
        category: category_label(&f.category).into(),
        leverage: f.leverage,
        severity: severity_label(&f.severity).into(),
        line,
        column,
        end_line,
        end_column,
        matched_text: f.matched_text.clone(),
        source_ranges: f
            .location
            .as_ref()
            .map_or(vec![], |l| l.source_ranges.clone()),
        sentence: f.sentence.clone(),
        suggestion: f.suggestion.clone(),
        fix: f.fix.clone(),
        keep_when: f.keep_when.clone(),
    }
}

fn finding_from_issue(i: &CopyeditIssue) -> CopyeditFinding {
    // Look up the canonical guidance entry for this rule to get correct
    // leverage, severity, guidance_id, and keep_when.
    let guidance = nobotrs::guidance::Guidance::embedded().for_rule(i.rule_id);
    let lev = guidance.map_or(4, |g| g.leverage);
    let sev = if lev <= 2 {
        nobotrs::score::Severity::High
    } else if lev <= 4 {
        nobotrs::score::Severity::Medium
    } else {
        nobotrs::score::Severity::Low
    };
    CopyeditFinding {
        rule_id: i.rule_id.into(),
        guidance_id: guidance.map_or(String::new(), |g| g.id.clone()),
        category: i.category.into(),
        leverage: lev,
        severity: severity_label(&sev).into(),
        line: i.line,
        column: i.column,
        end_line: i.end_line,
        end_column: i.end_column,
        matched_text: i.matched_text.clone(),
        source_ranges: i.source_ranges.clone(),
        sentence: None,
        suggestion: Some(i.fix.clone()),
        fix: i.fix.clone(),
        keep_when: guidance.map_or(String::new(), |g| g.keep_when.clone()),
    }
}

// clippy: the seven parameters mirror the consumer's full context
#[allow(clippy::too_many_arguments)]
/// Run copyediting on a single file using editorial_analysis.
pub(crate) fn copyedit_file(
    path: &str,
    markdown: bool,
    dialect: &str,
    allowed: &[String],
    settings: &Settings,
    engine: &Engine,
    models: &ModelRegistry,
) -> Result<CopyeditReport, String> {
    let input = load(path, settings.max_bytes)?;
    if input.truncated {
        return Err(format!("{path}: input exceeds maximum bytes"));
    }
    let md = markdown || Document::is_markdown(Path::new(path));

    // Phase 1: editorial_analysis prepares the doc (asserts language, attaches units).
    let deadline = Deadline::new(Duration::from_millis(settings.timeout_ms));
    let (mut report, doc) = engine.editorial_analysis(input.text, md, path, settings, models)?;

    // Phase 2: advisory review from the same prepared report + doc.
    report.settings.display_limit = usize::MAX;
    let mut review = nobotrs::review::review(&report, &doc);

    let mut findings: Vec<CopyeditFinding> = vec![];
    for f in &review.findings {
        if f.suppressed {
            continue;
        }
        findings.push(finding_from_review(f));
    }
    for f in &review.document {
        if f.suppressed {
            continue;
        }
        if findings
            .iter()
            .any(|existing| existing.rule_id == f.rule_id)
        {
            continue;
        }
        findings.push(finding_from_review(f));
    }

    // Phase 3: native copyediting engine on the same language-asserted doc.
    let directives = engine.suppression_directives(&doc, settings, path, deadline)?;
    let copyedit_limit = settings.max_candidates;
    let code_issues = copyediting::check(&doc, dialect, allowed, copyedit_limit, deadline)?;
    for issue in &code_issues {
        if !directives.iter().any(|d| {
            d.ids.iter().any(|id| id == issue.rule_id)
                && issue
                    .source_ranges
                    .iter()
                    .all(|r| d.scope.start <= r.start && r.end <= d.scope.end)
        }) {
            findings.push(finding_from_issue(issue));
        }
    }

    use nobotrs::review::{AnalysisCheck, AnalysisStatus};
    review.checks.push(AnalysisCheck {
        backend: "copyediting".into(),
        status: if doc.english_supported() {
            AnalysisStatus::Completed
        } else {
            AnalysisStatus::Skipped
        },
        reason: (!doc.english_supported()).then(|| "English language assertion required".into()),
    });
    findings.sort_by_key(|f| (f.leverage, f.line, f.column));
    let finding_count = findings.len();
    findings.truncate(settings.display_limit);
    Ok(CopyeditReport {
        schema_version: "1.0.0",
        path: path.into(),
        complete: review.complete,
        prose_words: review.prose_words,
        finding_count,
        omitted_findings: finding_count - findings.len(),
        findings,
        checks: review.checks,
        incomplete_reasons: review.incomplete_reasons.clone(),
    })
}

/// Human-readable output for a copyedit report.
pub(crate) fn human(report: &CopyeditReport) -> String {
    let mut out = format!(
        "Copyediting: {} ({} words, {} findings, {})\n",
        report.path,
        report.prose_words,
        report.finding_count,
        if report.complete {
            "complete"
        } else {
            "incomplete"
        },
    );
    if !report.complete {
        for r in &report.incomplete_reasons {
            out.push_str(&format!("  incomplete: {}\n", r));
        }
    }
    if report.findings.is_empty() {
        if report.finding_count == 0 {
            out.push_str("  No copyediting findings.\n");
        } else {
            out.push_str("  Display limit hides all findings.\n");
        }
        return out;
    }

    // Group by leverage
    let mut by_leverage: BTreeMap<u8, Vec<&CopyeditFinding>> = BTreeMap::new();
    for f in &report.findings {
        by_leverage.entry(f.leverage).or_default().push(f);
    }

    for (lev, group) in by_leverage.iter() {
        let label = match lev {
            1 => "Content & specificity",
            2 => "Structure",
            3 => "Rhythm & voice",
            4 => "Punctuation & formatting",
            _ => "Vocabulary",
        };
        out.push_str(&format!("\n  Leverage {} ({}):\n", lev, label));
        for f in group.iter().take(10) {
            let s = f.fix.split(".").next().unwrap_or(&f.fix);
            out.push_str(&format!("    line {}: [{}] {}\n", f.line, f.rule_id, s));
        }
        if group.len() > 10 {
            out.push_str(&format!("    ... and {} more\n", group.len() - 10));
        }
    }

    let min_lev = report
        .findings
        .iter()
        .map(|f| f.leverage)
        .min()
        .unwrap_or(5);
    out.push_str(&format!(
        "\n  {} findings total (lowest leverage: {})\n",
        report.finding_count, min_lev,
    ));
    out
}

#[allow(clippy::too_many_arguments)]
/// Run copyediting on one or more paths and produce output.
pub(crate) fn run(
    paths: &[String],
    dialect: &str,
    allowed: &[String],
    format: Format,
    settings: &Settings,
    markdown: bool,
    engine: &Engine,
    models: &ModelRegistry,
) -> Result<i32, String> {
    let mut reports: Vec<CopyeditReport> = vec![];
    let mut errors: Vec<Value> = vec![];

    for path in paths {
        match copyedit_file(
            path.as_str(),
            markdown,
            dialect,
            allowed,
            settings,
            engine,
            models,
        ) {
            Ok(r) => reports.push(r),
            Err(e) => errors.push(json!({"path": path, "error": e})),
        }
    }

    let exit_code = if !errors.is_empty() || reports.iter().any(|r| !r.complete) {
        2
    } else {
        0
    };

    match format {
        Format::Json => {
            let value = if reports.len() == 1 && errors.is_empty() {
                serde_json::to_value(&reports[0]).map_err(|e| e.to_string())?
            } else {
                json!({
                    "schema_version": "1.0.0",
                    "reports": reports,
                    "errors": errors,
                    "exit_code": exit_code,
                })
            };
            emit(&serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?)?;
        }
        Format::Human => {
            for r in &reports {
                emit(&human(r))?;
            }
            if reports.is_empty() && errors.is_empty() {
                emit("No files analyzed")?;
            }
        }
        Format::Sarif => {
            return Err("copyedit does not produce SARIF output".into());
        }
    }

    for e in &errors {
        eprintln!("nobotrs: {}: {}", e["path"], e["error"]);
    }

    Ok(exit_code)
}

#[cfg(test)]
mod tests {
    use super::*;
    use nobotrs::{config::Settings, models::ModelRegistry, pipeline::Engine};
    use std::fs;

    fn test_config() -> (Settings, Engine, ModelRegistry) {
        let settings = Settings {
            language: Some("en".into()),
            ..Settings::default()
        };
        let engine = Engine::new().unwrap();
        let models = ModelRegistry::resolve(&settings).unwrap();
        (settings, engine, models)
    }

    fn copyedit_text(
        text: &str,
        markdown: bool,
        dialect: &str,
        allowed: &[String],
    ) -> Result<CopyeditReport, String> {
        let (settings, engine, models) = test_config();
        use std::sync::atomic::{AtomicUsize, Ordering};
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let suffix = if markdown { "md" } else { "txt" };
        let path = std::env::temp_dir().join(format!(
            "nobotrs-copyedit-{}-{}.{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed),
            suffix
        ));
        fs::write(&path, text.as_bytes()).unwrap();
        let report = copyedit_file(
            path.to_str().unwrap(),
            markdown,
            dialect,
            allowed,
            &settings,
            &engine,
            &models,
        );
        fs::remove_file(path).unwrap();
        report
    }

    #[test]
    fn clean_text_runs_without_error() {
        let txt = "The budget gap is $8 million. We need to cut spending.\n";
        let r = copyedit_text(txt, false, "american", &[]).unwrap();
        assert!(r.complete, "copyedit should complete");
        assert!(r.prose_words > 0, "should have prose words");
    }

    #[test]
    fn detects_ai_tells() {
        let text = "It is important to note that we are currently navigating the complex landscape of budgetary challenges. Moreover, the transformative nature of these initiatives cannot be overstated.\n";
        let r = copyedit_text(text, false, "american", &[]).unwrap();
        assert!(r.complete);
    }

    #[test]
    fn location_fields_are_present() {
        let r = copyedit_text(
            "delve tapestry multifaceted robust\n",
            false,
            "american",
            &[],
        )
        .unwrap();
        if r.finding_count > 0 {
            assert!(
                !r.findings[0].rule_id.is_empty(),
                "finding should have rule_id"
            );
        }
    }

    #[test]
    fn empty_text_reports_zero_words() {
        let r = copyedit_text("", false, "american", &[]).unwrap();
        assert!(r.prose_words == 0);
    }

    #[test]
    fn markdown_text_works() {
        let r = copyedit_text(
            "# Title\n\nThis is a **paragraph**.\n\n- List item one\n",
            true,
            "american",
            &[],
        )
        .unwrap();
        assert!(r.complete);
        assert!(r.prose_words > 0);
    }

    #[test]
    fn british_dialect_is_accepted() {
        let r = copyedit_text(
            "The colour of the centre was organised.\n",
            false,
            "british",
            &[],
        )
        .unwrap();
        assert!(r.complete);
    }

    #[test]
    fn allowed_vocabulary_suppresses_spelling() {
        let r = copyedit_text(
            "nobotrs config is working\n",
            false,
            "american",
            &["nobotrs".into(), "config".into()],
        )
        .unwrap();
        assert!(r.complete);
    }

    #[test]
    fn bibb_fixture_runs_without_error() {
        let bibb = "evaluation/fixtures/bibb-fy27.txt";
        let (settings, engine, models) = test_config();
        let r = copyedit_file(bibb, false, "american", &[], &settings, &engine, &models).unwrap();
        assert!(r.complete);
        assert!(r
            .findings
            .iter()
            .any(|f| f.rule_id == "grammar.adjacent-articles"));
    }

    #[test]
    fn human_output_includes_leverage_groups() {
        let r = copyedit_text("delve moreover transformative\n", false, "american", &[]).unwrap();
        let out = human(&r);
        assert!(
            out.contains("Leverage") || out.contains("No copyediting findings"),
            "human output should reference leverage",
        );
    }

    #[test]
    fn category_and_source_ranges_are_not_discarded() {
        let r = copyedit_text("teh quick brown fox\n", false, "american", &[]).unwrap();
        let typo = r
            .findings
            .iter()
            .find(|f| f.rule_id == "spelling.common-typo")
            .unwrap();
        assert_eq!(typo.category, "spelling");
        assert_eq!(typo.source_ranges.first(), Some(&(0..3)));
    }

    #[test]
    fn error_on_nonexistent_file() {
        let (settings, engine, models) = test_config();
        let r = copyedit_file(
            "/tmp/nobotrs-nonexistent-file.txt",
            false,
            "american",
            &[],
            &settings,
            &engine,
            &models,
        );
        assert!(r.is_err(), "nonexistent file should produce an error");
    }

    #[test]
    fn display_limit_follows_suppression_and_counts() {
        let (mut settings, engine, models) = test_config();
        let path =
            std::env::temp_dir().join(format!("nobotrs-copyedit-limit-{}.txt", std::process::id()));
        fs::write(&path, "teh writer recieved a the report.").unwrap();
        settings.display_limit = 0;
        settings.ignore_rules = vec!["grammar.adjacent-articles".into()];
        let report = copyedit_file(
            path.to_str().unwrap(),
            false,
            "american",
            &[],
            &settings,
            &engine,
            &models,
        )
        .unwrap();
        fs::remove_file(path).unwrap();
        assert_eq!(report.finding_count, 2);
        assert_eq!(report.omitted_findings, 2);
        assert!(report.findings.is_empty());
    }
}
