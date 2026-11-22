use super::{
    emit,
    invariants::{self, Invariant},
    load, Format,
};
use nobotrs::{
    backend::ScoreOutcome, config::Settings, document::Document, pipeline::Engine,
    review::ReviewReport,
};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};
type Counts = BTreeMap<(u8, String, String, String), usize>;

struct Draft {
    facts: Vec<Invariant>,
    review: ReviewReport,
    metrics: BTreeMap<String, f64>,
    sections: Vec<super::sections::Section>,
    model_outputs: BTreeMap<String, f64>,
}
fn read_draft(
    path: &str,
    markdown: bool,
    settings: &Settings,
    engine: &Engine,
    models: &nobotrs::models::ModelRegistry,
) -> Result<Draft, String> {
    let input = load(path, settings.max_bytes)?;
    if input.truncated {
        return Err(format!("{path}: input exceeds maximum bytes"));
    }
    let md = markdown || Document::is_markdown(Path::new(path));
    let (report, doc) = engine.editorial_analysis(input.text, md, path, settings, models)?;
    let facts = invariants::extract(
        &doc,
        settings.max_candidates,
        nobotrs::deadline::Deadline::new(std::time::Duration::from_millis(settings.timeout_ms)),
    )?;
    let mut metrics = BTreeMap::from([("prose_words".to_string(), report.prose_words as f64)]);
    for backend in &report.backends {
        if let ScoreOutcome::Scored(score) = &backend.outcome {
            for (name, metric) in &score.metrics {
                if matches!(
                    name.as_str(),
                    "sentence_length_cv"
                        | "em_dashes_per_100_words"
                        | "mtld"
                        | "flesch_kincaid_grade"
                ) {
                    metrics.insert(name.to_string(), metric.value);
                }
            }
        }
    }
    let review = nobotrs::review::review(&report, &doc);
    let (sections, model_outputs) = if settings.models.is_empty() {
        Default::default()
    } else {
        super::sections::collect(&report, &doc)
    };
    Ok(Draft {
        sections,
        model_outputs,
        facts,
        review,
        metrics,
    })
}
fn counts(report: &ReviewReport) -> Counts {
    let mut result = Counts::new();
    for f in report
        .findings
        .iter()
        .chain(&report.document)
        .filter(|f| !f.suppressed)
    {
        *result
            .entry((
                f.leverage,
                f.rule_id.clone(),
                f.guidance_id.clone(),
                f.matched_text.clone(),
            ))
            .or_default() += 1;
    }
    result
}
pub(super) fn run(
    before: &str,
    after: &str,
    accept_missing: &[String],
    format: Format,
    settings: &Settings,
    markdown: bool,
    engine: &Engine,
) -> Result<i32, String> {
    if before == "-" && after == "-" {
        return Err("stdin can supply only one draft".into());
    }
    if matches!(format, Format::Sarif) {
        return Err("compare supports human or json output".into());
    }
    let mut full = settings.clone();
    full.display_limit = 100_000;
    let models = nobotrs::models::ModelRegistry::resolve(&full)?;
    let left = read_draft(before, markdown, &full, engine, &models)?;
    let right = read_draft(after, markdown, &full, engine, &models)?;
    let (l, r) = (counts(&left.review), counts(&right.review));
    let (mut removed, mut introduced, mut kept) = (Vec::new(), Vec::new(), Vec::new());
    for key in l.keys().chain(r.keys()).collect::<BTreeSet<_>>() {
        let a = l.get(key).copied().unwrap_or(0);
        let b = r.get(key).copied().unwrap_or(0);
        let item = |count| json!({"rule_id":key.1,"guidance_id":key.2,"leverage":key.0,"matched_text":key.3,"before":a,"after":b,"count":count});
        if a > b {
            removed.push(item(a - b))
        }
        if b > a {
            introduced.push(item(b - a))
        }
        if a.min(b) > 0 {
            kept.push(item(a.min(b)))
        }
    }
    let all_missing = invariants::difference(&left.facts, &right.facts);
    let mut confirmed = BTreeSet::new();
    for accept in accept_missing {
        if !all_missing
            .iter()
            .any(|i| format!("{}={}", i.kind, i.text) == *accept)
        {
            return Err(format!(
                "confirmation matches no missing invariant: {accept}"
            ));
        }
        confirmed.insert(accept);
    }
    let (approved, missing): (Vec<_>, Vec<_>) = all_missing
        .into_iter()
        .partition(|i| confirmed.contains(&format!("{}={}", i.kind, i.text)));
    let added: Vec<_> = invariants::difference(&right.facts, &left.facts)
        .into_iter()
        .map(|i| json!({"invariant":i,"status":"confirm_source"}))
        .collect();
    let complete = left.review.complete && right.review.complete;
    let code = if !complete {
        2
    } else if missing.iter().any(Invariant::hard) {
        1
    } else {
        0
    };
    let metrics: Vec<_> = left
        .metrics
        .keys()
        .chain(right.metrics.keys())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .map(|k| json!({"name":k,"before":left.metrics.get(k),"after":right.metrics.get(k)}))
        .collect();
    let mut checklist = serde_json::to_value(&right.review.checklist).map_err(|e| e.to_string())?;
    if !added.is_empty() || !missing.is_empty() {
        for item in checklist.as_array_mut().into_iter().flatten() {
            if item["id"] == "facts-are-real" {
                item["status"] = json!("fail");
                item["detail"] = json!("Review changed claims against the source.");
            }
        }
    }
    let message="Check attribution, negation, obligations and time scope against the source. Matching names and numbers alone cannot establish fidelity.";
    let section_deltas = super::sections::align(
        &left.sections,
        &right.sections,
        nobotrs::deadline::Deadline::new(std::time::Duration::from_millis(settings.timeout_ms)),
    )?;
    let model_deltas:Vec<_>=left.model_outputs.keys().chain(right.model_outputs.keys()).collect::<BTreeSet<_>>().into_iter().map(|k|json!({"name":k,"before":left.model_outputs.get(k),"after":right.model_outputs.get(k)})).collect();
    if matches!(format, Format::Json) {
        let mut result = json!({"schema_version":"1.0.0","compare_version":"compare-v1","before":before,"after":after,"complete":complete,"removed":removed,"kept":kept,"introduced":introduced,"leverage_before":left.review.leverage_counts,"leverage_after":right.review.leverage_counts,"metrics":metrics,"missing":missing,"added":added,"accepted_missing":approved,"checklist_after":checklist,"semantic_review":message,"exit_code":code});
        if !section_deltas.is_empty() || !model_deltas.is_empty() {
            result["section_deltas"] = json!(section_deltas);
            result["full_coverage_outputs"] = json!(model_deltas);
        }
        emit(&result.to_string())?;
    } else {
        let total =
            |rows: &Vec<Value>| rows.iter().filter_map(|x| x["count"].as_u64()).sum::<u64>();
        emit(&format!(
            "Removed {} findings, kept {}, introduced {}.",
            total(&removed),
            total(&kept),
            total(&introduced)
        ))?;
        for i in &missing {
            emit(&format!(
                "MISSING {before}:{}:{}  {}: {}",
                i.line, i.column, i.kind, i.text
            ))?;
        }
        for row in &added {
            let i = &row["invariant"];
            emit(&format!(
                "CONFIRM {after}:{}:{}  {}: {}",
                i["line"], i["column"], i["kind"], i["text"]
            ))?;
        }
        for row in metrics {
            emit(&format!(
                "{}: {} → {}",
                row["name"], row["before"], row["after"]
            ))?;
        }
        for section in section_deltas {
            emit(&format!(
                "{} section {} (lines {:?} → {:?}, classifier z {:?} → {:?})",
                section.status,
                section.heading.as_deref().unwrap_or("(unheaded)"),
                section.before_lines,
                section.after_lines,
                section.before_mean_z,
                section.after_mean_z
            ))?;
        }
        emit(message)?;
        if !complete {
            emit("Analysis incomplete. Review the source files directly.")?
        }
    }
    Ok(code)
}
