//! Reproducible local owner-corpus baseline with one registry and per-document checkpoints.
use clap::Parser;
use nobotrs::{
    backend::ScoreOutcome,
    config::{ModelCoverage, Settings},
    models::ModelRegistry,
    pipeline::Engine,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    time::Instant,
};
#[derive(Parser)]
struct Args {
    #[arg(long)]
    allow_multiple_models: bool,
    #[arg(long)]
    models_dir: PathBuf,
    #[arg(long, default_value = "evaluation/corpora/owner-posts-v1")]
    corpus: PathBuf,
    #[arg(long)]
    out: PathBuf,
    #[arg(long, default_value_t = 1_200_000)]
    timeout_ms: u64,
    #[arg(long)]
    limit: Option<usize>,
}
fn write(path: &Path, value: &Value) -> Result<(), Box<dyn std::error::Error>> {
    let temporary = path.with_extension("json.tmp");
    std::fs::write(&temporary, serde_json::to_vec_pretty(value)?)?;
    std::fs::rename(temporary, path)?;
    Ok(())
}
fn hash(path: &Path) -> Result<String, Box<dyn std::error::Error>> {
    Ok(format!("{:x}", Sha256::digest(std::fs::read(path)?)))
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();
    if !args.allow_multiple_models {
        return Err("use --example owner_model_sweep for bounded single-model recovery; historical multi-model reproduction requires --allow-multiple-models".into());
    }
    let started = Instant::now();
    let manifest_path = args.corpus.join("manifest.json");
    let manifest: Value = serde_json::from_slice(&std::fs::read(&manifest_path)?)?;
    let mut posts: Vec<_> = manifest["posts"]
        .as_array()
        .ok_or("owner manifest posts")?
        .iter()
        .collect();
    posts.sort_by_key(|p| p["file"].as_str().unwrap_or(""));
    if let Some(n) = args.limit {
        posts.truncate(n);
    }
    let settings = Settings {
        models: vec!["desklib".into(), "conpara".into(), "detectorscope".into()],
        models_dir: Some(args.models_dir),
        model_coverage: ModelCoverage::Full,
        language: Some("en".into()),
        timeout_ms: args.timeout_ms,
        display_limit: 100_000,
        minimum_severity: nobotrs::score::Severity::Low,
        ..Default::default()
    };
    assert!(!settings.gptzero && !settings.openrouter_judge);
    let registry = ModelRegistry::resolve(&settings)?;
    let engine = Engine::new()?;
    std::fs::create_dir_all(&args.out)?;
    let revision = std::process::Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()?;
    let source_dirty = !std::process::Command::new("git")
        .args([
            "diff",
            "--quiet",
            "HEAD",
            "--",
            "src",
            "examples",
            "Cargo.toml",
            "Cargo.lock",
            "build.rs",
            "integrations/model_workers",
        ])
        .status()?
        .success();
    let mut run = json!({"schema_version":"owner-model-baseline-v1","argv":std::env::args().collect::<Vec<_>>(),"source_dirty":source_dirty,"worker_python":std::env::var("NOBOTRS_MODEL_PYTHON").ok(),"git_revision":String::from_utf8_lossy(&revision.stdout).trim(),"binary_sha256":hash(&std::env::current_exe()?)?,"corpus_manifest_sha256":hash(&manifest_path)?,"settings":settings,"external":"none","configuration":"constructed from Settings::default plus recorded overrides; no environment or config-file merging","features":["models-encoders","models-detectorscope"],"models":nobotrs::models::manifests(),"registry_reused":true,"sample_limit":args.limit,"planned_documents":posts.len(),"completed_documents":0,"finished":false,"documents":[],"backend_status_counts":{}});
    let mut counts: BTreeMap<String, BTreeMap<String, usize>> = BTreeMap::new();
    let mut documents = Vec::new();
    write(&args.out.join("run.json"), &run)?;
    for (i, post) in posts.iter().enumerate() {
        let filename = post["file"].as_str().ok_or("owner manifest filename")?;
        let path = args.corpus.join("samples").join(filename);
        let input_sha256 = hash(&path)?;
        if post["sha256"].as_str() != Some(input_sha256.as_str()) {
            return Err(format!("owner source checksum mismatch: {filename}").into());
        }
        let raw = std::fs::read_to_string(&path)?;
        println!("START {}/{} {}", i + 1, posts.len(), filename);
        let doc_started = Instant::now();
        let mut entry = json!({"file":filename,"label":post["label"],"confidence":post["confidence"],"input_sha256":hash(&path)?});
        let stem = Path::new(filename).file_stem().ok_or("filename stem")?;
        let out = args.out.join(stem);
        std::fs::create_dir_all(&out)?;
        match engine.editorial_analysis(
            raw,
            true,
            path.to_str().ok_or("UTF-8 owner path")?,
            &settings,
            &registry,
        ) {
            Ok((report, doc)) => {
                let review = nobotrs::review::review(&report, &doc);
                let mut per_backend = BTreeMap::new();
                for model in &settings.models {
                    let status = match report
                        .backends
                        .iter()
                        .find(|b| &b.backend == model)
                        .map(|b| &b.outcome)
                    {
                        Some(ScoreOutcome::Scored(s))
                            if s.model_evidence
                                .as_ref()
                                .is_some_and(|e| e.token_coverage == Some(1.0)) =>
                        {
                            "scored_full"
                        }
                        Some(ScoreOutcome::Scored(_)) => "missing_full_evidence",
                        Some(ScoreOutcome::Incomplete { .. }) => "incomplete",
                        Some(ScoreOutcome::Abstained { .. }) => "skipped",
                        Some(ScoreOutcome::Failed(_)) => "failed",
                        None => "missing",
                    };
                    *counts
                        .entry(model.clone())
                        .or_default()
                        .entry(status.into())
                        .or_default() += 1;
                    per_backend.insert(model.clone(), status);
                }
                entry["backends"] = json!(per_backend);
                entry["complete"] = json!(report.complete);
                entry["prose_words"] = json!(report.prose_words);
                entry["review_exit_code"] = json!(if review.complete { 0 } else { 2 });
                entry["report_detection_exit_code"] = json!(report.exit_code(false));
                write(&out.join("report.json"), &serde_json::to_value(&report)?)?;
                write(&out.join("review.json"), &serde_json::to_value(&review)?)?;
            }
            Err(error) => {
                entry["operational_error"] = json!(error);
                entry["complete"] = json!(false);
                for model in &settings.models {
                    *counts
                        .entry(model.clone())
                        .or_default()
                        .entry("missing_operational_error".into())
                        .or_default() += 1;
                }
            }
        }
        entry["elapsed_ms"] = json!(doc_started.elapsed().as_secs_f64() * 1000.0);
        println!(
            "DONE {}/{} {} {:.1}s {}",
            i + 1,
            posts.len(),
            filename,
            doc_started.elapsed().as_secs_f64(),
            entry["backends"]
        );
        documents.push(entry);
        run["documents"] = json!(documents);
        run["completed_documents"] = json!(documents.len());
        run["backend_status_counts"] = json!(counts);
        run["elapsed_ms"] = json!(started.elapsed().as_secs_f64() * 1000.0);
        write(&args.out.join("run.json"), &run)?;
    }
    run["finished"] = json!(true);
    run["elapsed_ms"] = json!(started.elapsed().as_secs_f64() * 1000.0);
    write(&args.out.join("run.json"), &run)?;
    println!(
        "FINISHED {} documents in {:.1}s: {}",
        documents.len(),
        started.elapsed().as_secs_f64(),
        serde_json::to_string(&counts)?
    );
    Ok(())
}
