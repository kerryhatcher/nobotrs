//! Single-model resumable owner-corpus sweep. No overlapping model copies.
use clap::Parser;
use nobotrs::{
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
    #[arg(long,value_parser=["desklib","conpara","detectorscope"])]
    model: String,
    #[arg(long)]
    models_dir: PathBuf,
    #[arg(long, default_value = "evaluation/corpora/owner-posts-v1")]
    corpus: PathBuf,
    #[arg(long)]
    out: PathBuf,
    #[arg(long)]
    resume_from: Vec<PathBuf>,
    #[arg(long, default_value_t = 1_200_000)]
    timeout_ms: u64,
    #[arg(long, default_value_t = 4096)]
    minimum_available_mib: u64,
    #[arg(long)]
    limit: Option<usize>,
}
fn write(path: &Path, value: &Value) -> Result<(), Box<dyn std::error::Error>> {
    let temp = path.with_extension("json.tmp");
    std::fs::write(&temp, serde_json::to_vec_pretty(value)?)?;
    std::fs::rename(temp, path)?;
    Ok(())
}
fn hash(path: &Path) -> Result<String, Box<dyn std::error::Error>> {
    Ok(format!("{:x}", Sha256::digest(std::fs::read(path)?)))
}
fn available() -> Result<u64, Box<dyn std::error::Error>> {
    let text = std::fs::read_to_string("/proc/meminfo")?;
    let value = text
        .lines()
        .find_map(|l| l.strip_prefix("MemAvailable:"))
        .ok_or("MemAvailable unavailable")?
        .split_whitespace()
        .next()
        .ok_or("MemAvailable value")?
        .parse::<u64>()?;
    Ok(value / 1024)
}
fn terminal(backend: &Value) -> bool {
    let o = &backend["outcome"];
    o["status"] == "abstained"
        || (o["status"] == "scored" && o["details"]["model_evidence"]["token_coverage"] == 1.0)
}
fn status(backend: &Value) -> &'static str {
    match backend["outcome"]["status"].as_str() {
        Some("scored") if terminal(backend) => "scored_full",
        Some("abstained") => "skipped",
        Some("incomplete") => "incomplete",
        Some("failed") => "failed",
        _ => "missing_full_evidence",
    }
}
fn previous(args: &Args, stem: &std::ffi::OsStr) -> Option<(Value, PathBuf)> {
    let own = args.out.join(stem).join("backend.json");
    if let Ok(bytes) = std::fs::read(&own) {
        if let Ok(v) = serde_json::from_slice::<Value>(&bytes) {
            if terminal(&v) {
                return Some((v, own));
            }
        }
    }
    for root in &args.resume_from {
        let path = root.join(stem).join("report.json");
        let Ok(bytes) = std::fs::read(&path) else {
            continue;
        };
        let Ok(v) = serde_json::from_slice::<Value>(&bytes) else {
            continue;
        };
        if v["settings"]["model_coverage"] != "full" {
            continue;
        }
        let Some(b) = v["backends"]
            .as_array()
            .and_then(|a| a.iter().find(|b| b["backend"] == args.model))
        else {
            continue;
        };
        if terminal(b) {
            return Some((b.clone(), path));
        }
    }
    None
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();
    let started = Instant::now();
    let manifest_path = args.corpus.join("manifest.json");
    let manifest: Value = serde_json::from_slice(&std::fs::read(&manifest_path)?)?;
    let mut posts: Vec<_> = manifest["posts"]
        .as_array()
        .ok_or("owner manifest")?
        .iter()
        .collect();
    posts.sort_by_key(|p| p["file"].as_str().unwrap_or(""));
    // Stable partition: resolved results are reused, untouched documents run next,
    // and failed/incomplete prior attempts are retried only after all first attempts.
    let mut ordered = Vec::new();
    for post in posts {
        let stem = Path::new(post["file"].as_str().ok_or("filename")?)
            .file_stem()
            .ok_or("stem")?;
        let mut prior = None;
        let own = args.out.join(stem).join("backend.json");
        if let Ok(bytes) = std::fs::read(&own) {
            prior = serde_json::from_slice::<Value>(&bytes).ok();
        }
        if prior.is_none() {
            for root in &args.resume_from {
                if let Ok(bytes) = std::fs::read(root.join(stem).join("report.json")) {
                    if let Ok(report) = serde_json::from_slice::<Value>(&bytes) {
                        prior = report["backends"]
                            .as_array()
                            .and_then(|a| a.iter().find(|b| b["backend"] == args.model))
                            .cloned();
                        if prior.is_some() {
                            break;
                        }
                    }
                }
            }
        }
        let order = match prior {
            Some(ref b) if terminal(b) => 0,
            Some(_) => 2,
            None => 1,
        };
        ordered.push((order, post));
    }
    ordered.sort_by_key(|(order, _)| *order);
    let mut posts: Vec<_> = ordered.into_iter().map(|(_, post)| post).collect();
    if let Some(n) = args.limit {
        posts.truncate(n);
    }
    let settings = Settings {
        models: vec![args.model.clone()],
        models_dir: Some(args.models_dir.clone()),
        model_coverage: ModelCoverage::Full,
        language: Some("en".into()),
        timeout_ms: args.timeout_ms,
        display_limit: 100_000,
        minimum_severity: nobotrs::score::Severity::Low,
        ..Default::default()
    };
    let engine = Engine::new()?;
    let mut registry = None;
    std::fs::create_dir_all(&args.out)?;
    let rev = std::process::Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()?;
    if args.out.join("run.json").exists() {
        let n = (1..)
            .find(|n| !args.out.join(format!("run-attempt-{n}.json")).exists())
            .unwrap();
        std::fs::copy(
            args.out.join("run.json"),
            args.out.join(format!("run-attempt-{n}.json")),
        )?;
    }
    let mut run = json!({"schema_version":"owner-model-sweep-v1","model":args.model,"argv":std::env::args().collect::<Vec<_>>(),"git_revision_at_start":String::from_utf8_lossy(&rev.stdout).trim(),"binary_sha256":hash(&std::env::current_exe()?)?,"manifest_sha256":hash(&manifest_path)?,"settings":settings,"external":"none","registry_reused_within_sweep":true,"model_concurrency":1,"runtime_threads":{"rayon":std::env::var("RAYON_NUM_THREADS").ok(),"torch":std::env::var("NOBOTRS_MODEL_THREADS").ok()},"planned_documents":posts.len(),"resolved_documents":0,"finished":false,"documents":[],"status_counts":{}});
    let mut documents = Vec::new();
    let mut counts = BTreeMap::<String, usize>::new();
    write(&args.out.join("run.json"), &run)?;
    for (i, post) in posts.iter().enumerate() {
        let filename = post["file"].as_str().ok_or("filename")?;
        let path = args.corpus.join("samples").join(filename);
        let sha = hash(&path)?;
        if post["sha256"] != sha {
            return Err(format!("source checksum mismatch: {filename}").into());
        }
        let stem = Path::new(filename).file_stem().ok_or("stem")?;
        let out = args.out.join(stem);
        std::fs::create_dir_all(&out)?;
        let begin = Instant::now();
        let mut entry = json!({"file":filename,"label":post["label"],"confidence":post["confidence"],"input_sha256":sha});
        let backend = if let Some((backend, source)) = previous(&args, stem) {
            entry["reused_from"] = json!(source);
            entry["reused_source_sha256"] = json!(hash(&source)?);
            backend
        } else {
            let free = available()?;
            if free < args.minimum_available_mib {
                run["deferred"] = json!({"file":filename,"available_mib":free,"required_mib":args.minimum_available_mib});
                write(&args.out.join("run.json"), &run)?;
                return Err("available memory below sweep headroom; checkpoints preserved".into());
            }
            if registry.is_none() {
                registry = Some(ModelRegistry::resolve(&settings)?);
            }
            println!(
                "START {}/{} {} {} available={}MiB",
                i + 1,
                posts.len(),
                args.model,
                filename,
                free
            );
            run["active_document"] = json!(filename);
            write(&args.out.join("run.json"), &run)?;
            let raw = std::fs::read_to_string(&path)?;
            let (report, doc) = engine.editorial_analysis(
                raw,
                true,
                path.to_str().ok_or("UTF8 path")?,
                &settings,
                registry.as_ref().unwrap(),
            )?;
            let backend = report
                .backends
                .iter()
                .find(|b| b.backend == args.model)
                .ok_or("missing requested model")?;
            let backend = serde_json::to_value(backend)?;
            let attempt = (1..)
                .find(|n| !out.join(format!("backend-attempt-{n}.json")).exists())
                .unwrap();
            write(
                &out.join(format!("backend-attempt-{attempt}.json")),
                &backend,
            )?;
            write(
                &out.join(format!("report-attempt-{attempt}.json")),
                &serde_json::to_value(&report)?,
            )?;
            write(
                &out.join(format!("review-attempt-{attempt}.json")),
                &serde_json::to_value(nobotrs::review::review(&report, &doc))?,
            )?;
            entry["attempt"] = json!(attempt);
            entry["report_source"] = json!(out.join(format!("report-attempt-{attempt}.json")));
            backend
        };
        let state = status(&backend);
        entry["status"] = json!(state);
        entry["elapsed_ms"] = json!(begin.elapsed().as_secs_f64() * 1000.0);
        if !out.join("backend.json").exists() || entry.get("reused_from").is_none() {
            write(&out.join("backend.json"), &backend)?;
        }
        println!(
            "DONE {}/{} {} {} {} {:.1}s",
            i + 1,
            posts.len(),
            args.model,
            filename,
            state,
            begin.elapsed().as_secs_f64()
        );
        *counts.entry(state.into()).or_default() += 1;
        write(&out.join("entry.json"), &entry)?;
        documents.push(entry);
        run["active_document"] = Value::Null;
        run["documents"] = json!(documents);
        run["resolved_documents"] = json!(documents.len());
        run["status_counts"] = json!(counts);
        run["elapsed_ms"] = json!(started.elapsed().as_secs_f64() * 1000.0);
        write(&args.out.join("run.json"), &run)?;
    }
    run["finished"] = json!(true);
    write(&args.out.join("run.json"), &run)?;
    println!(
        "FINISHED {} {}",
        args.model,
        serde_json::to_string(&counts)?
    );
    Ok(())
}
