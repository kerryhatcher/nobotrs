mod compare;
mod copyedit;
mod facts;
mod invariants;
mod sections;
use clap::{Parser, Subcommand, ValueEnum};
use nobotrs::{
    config::{Overrides, ResolvedConfig},
    pipeline::{read_bounded, Engine, ReadInput, Report},
};
use std::{
    io::{self, Write},
    path::{Path, PathBuf},
};
#[derive(Clone, Copy, ValueEnum)]
pub enum Format {
    Human,
    Json,
    Sarif,
}
#[derive(Parser)]
#[command(
    name = "nobotrs",
    version,
    about = "Offline heuristic prose linter and detector (uncalibrated)"
)]
pub struct Cli {
    #[arg(long, global = true, value_enum, default_value = "human")]
    format: Format,
    #[arg(long, global = true)]
    config: Option<PathBuf>,
    /// Treat stdin or a file as Markdown.
    #[arg(long, global = true)]
    markdown: bool,
    /// Assert a language (en enables English-specific metrics).
    #[arg(long, global = true)]
    language: Option<String>,
    /// Comma-separated optional local model evidence backends: desklib,conpara,detectorscope.
    #[arg(long, global = true, value_delimiter = ',')]
    models: Vec<String>,
    /// Directory containing the pinned model artifacts described by models/*.json.
    #[arg(long, global = true)]
    models_dir: Option<PathBuf>,
    /// Optional local model coverage; full adds section diagnostics under the same deadline.
    #[arg(long, global = true, value_enum)]
    model_coverage: Option<nobotrs::config::ModelCoverage>,
    /// Opt-in: also send the text to GPTZero for an informational comparison (needs GPTZERO_API_KEY).
    /// Sends your text to a third party. Supported by `detect` and `analyze` only.
    #[arg(long, global = true)]
    gptzero: bool,
    /// Opt-in: ask an OpenRouter model to judge AI vs human, using the AI writing guide as reference.
    /// Sends your text to a third party. Needs OPENROUTER_API_KEY. Supported by `detect` and `analyze`.
    #[arg(long, global = true)]
    openrouter_judge: bool,
    #[arg(long, global = true)]
    quorum: Option<usize>,
    #[arg(long, global = true, value_enum)]
    minimum_severity: Option<nobotrs::score::Severity>,
    #[arg(long, global = true)]
    max_bytes: Option<usize>,
    #[arg(long, global = true)]
    max_candidates: Option<usize>,
    #[arg(long, global = true)]
    display_limit: Option<usize>,
    #[arg(long, global = true)]
    timeout_ms: Option<u64>,
    /// Comma-separated stable rule IDs; replaces configured global ignores.
    #[arg(long, global = true, value_delimiter = ',')]
    ignore_rule: Vec<String>,
    #[command(subcommand)]
    command: Command,
}
#[derive(Subcommand)]
pub enum Command {
    /// Compare editing findings and source-sensitive facts in two drafts.
    Compare {
        before: String,
        after: String,
        /// Accept an intentional removal, specified as KIND=EXACT_TEXT.
        #[arg(long)]
        accept_missing: Vec<String>,
    },
    /// Compare labelled quantities and dates in explicit project sources.
    Facts {
        #[command(subcommand)]
        command: FactsCommand,
    },
    /// Analyze a file or stdin (-) using a quorum of independent heuristic families.
    Detect { path: String },
    /// Report individual editing findings, independent of detection quorum.
    Lint {
        #[arg(required = true)]
        paths: Vec<String>,
    },
    /// Give an advisory offline editorial review, ordered by leverage.
    Review { path: String },
    /// Report raw metrics and backend outcomes for a file or stdin (-).
    Analyze { path: String },
    /// Batch detection of .txt, .md and .markdown files, in deterministic path order.
    Scan { dir: PathBuf },
    /// Show effective settings, override origins and offline backend availability.
    Config,
    /// Print the packaged writing guide.
    Guide,
    /// Print the full AI writing field guide.
    AiWritingGuide,
    /// Check grammar, spelling, style and readability for copyediting.
    Copyedit {
        #[arg(required = true)]
        paths: Vec<String>,
        /// Dialect for variant spelling rules: american (default) or british.
        #[arg(long, default_value = "american")]
        dialect: String,
        /// A word to allow (never flag). Repeatable.
        #[arg(long)]
        allow_word: Vec<String>,
    },
}
#[derive(Subcommand)]
pub enum FactsCommand {
    /// Compare one or more files. A reference establishes expected claims.
    Check {
        #[arg(required = true)]
        paths: Vec<String>,
        #[arg(long)]
        reference: Option<String>,
    },
}
pub fn run(cli: Cli) -> Result<i32, String> {
    if matches!(cli.command, Command::AiWritingGuide) {
        let guide = include_str!("../../docs/ai-writing-guide.md");
        match cli.format {
            Format::Human => io::stdout()
                .lock()
                .write_all(guide.as_bytes())
                .map_err(|e| format!("stdout: {e}"))?,
            Format::Json => {
                emit(&serde_json::json!({"schema_version": "1.0.0", "guide": guide}).to_string())?
            }
            Format::Sarif => return Err("ai-writing-guide does not produce SARIF".into()),
        }
        return Ok(0);
    }
    let mut resolved = ResolvedConfig::load(
        cli.config,
        Overrides {
            minimum_severity: cli.minimum_severity,
            quorum: cli.quorum,
            max_bytes: cli.max_bytes,
            max_candidates: cli.max_candidates,
            display_limit: cli.display_limit,
            timeout_ms: cli.timeout_ms,
            language: cli.language,
            models: if cli.models.is_empty() {
                None
            } else {
                Some(cli.models)
            },
            models_dir: cli.models_dir,
            model_coverage: cli.model_coverage,
            gptzero: if cli.gptzero { Some(true) } else { None },
            openrouter_judge: if cli.openrouter_judge {
                Some(true)
            } else {
                None
            },
            openrouter_strict_privacy: None,
            ignore_rules: if cli.ignore_rule.is_empty() {
                None
            } else {
                Some(cli.ignore_rule)
            },
        },
    )?;
    let engine = Engine::new()?;
    engine.validate_settings(&resolved.settings)?;
    if matches!(cli.command, Command::Config) {
        let value = serde_json::json!({"schema_version":"1.0.0","configuration":resolved,"backends":nobotrs::config::BACKENDS.iter().map(|name|serde_json::json!({"backend":name,"availability":"ready","enabled":resolved.settings.enabled_backends.iter().any(|n|n==name)})).collect::<Vec<_>>(),"models":nobotrs::models::statuses(&resolved.settings)});
        emit(&serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?)?;
        return Ok(0);
    }
    if matches!(cli.command, Command::Guide) {
        match cli.format {
            Format::Human => emit(&nobotrs::guidance::Guidance::embedded().brief)?,
            Format::Json => {
                let mut value = serde_json::to_value(nobotrs::guidance::Guidance::embedded())
                    .map_err(|e| e.to_string())?;
                value["guide"] = serde_json::json!(include_str!("../../docs/writing-guide.md"));
                emit(&serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?)?;
            }
            Format::Sarif => return Err("guide does not produce SARIF".into()),
        }
        return Ok(0);
    }
    let single_input = matches!(
        cli.command,
        Command::Detect { .. } | Command::Analyze { .. }
    );
    if resolved.settings.gptzero {
        if !single_input {
            return Err("--gptzero is supported by detect and analyze only".into());
        }
        if !cfg!(feature = "api-clients") {
            return Err(
                "this build has no GPTZero support; rebuild with --features api-clients".into(),
            );
        }
    }
    if resolved.settings.openrouter_judge {
        if !single_input {
            return Err("--openrouter-judge is supported by detect and analyze only".into());
        }
        if !cfg!(feature = "api-clients") {
            return Err(
                "this build has no OpenRouter support; rebuild with --features api-clients".into(),
            );
        }
    }
    if let Command::Facts {
        command: FactsCommand::Check { paths, reference },
    } = &cli.command
    {
        return facts::check(
            paths,
            reference.as_deref(),
            cli.format,
            &resolved.settings,
            cli.markdown,
        );
    }
    if let Command::Review { path } = &cli.command {
        if matches!(cli.format, Format::Sarif) {
            return Err("review does not produce SARIF".into());
        }
        if resolved
            .origins
            .get("minimum_severity")
            .is_some_and(|o| o == "default")
        {
            resolved.settings.minimum_severity = nobotrs::score::Severity::Low;
        }
        if !resolved.settings.models.is_empty()
            && resolved
                .origins
                .get("model_coverage")
                .is_some_and(|o| o == "default")
        {
            resolved.settings.model_coverage = nobotrs::config::ModelCoverage::Full;
        }
        let input = load(path, resolved.settings.max_bytes)?;
        let mut report = engine.review(
            input.text,
            cli.markdown || nobotrs::document::Document::is_markdown(Path::new(path)),
            path,
            &resolved.settings,
        )?;
        if input.truncated {
            report.mark_input_truncated();
        }
        match cli.format {
            Format::Json => {
                emit(&serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?)?
            }
            Format::Human => emit(&nobotrs::review::human(&report))?,
            Format::Sarif => unreachable!(),
        }
        return Ok(if report.complete { 0 } else { 2 });
    }
    if let Command::Compare {
        before,
        after,
        accept_missing,
    } = &cli.command
    {
        if resolved
            .origins
            .get("minimum_severity")
            .is_some_and(|o| o == "default")
        {
            resolved.settings.minimum_severity = nobotrs::score::Severity::Low;
        }
        if !resolved.settings.models.is_empty()
            && resolved
                .origins
                .get("model_coverage")
                .is_some_and(|o| o == "default")
        {
            resolved.settings.model_coverage = nobotrs::config::ModelCoverage::Full;
        }
        return compare::run(
            before,
            after,
            accept_missing,
            cli.format,
            &resolved.settings,
            cli.markdown,
            &engine,
        );
    }
    // Retain the registry across inputs so analysis can reuse loaded models.
    let models = nobotrs::models::ModelRegistry::resolve(&resolved.settings)?;
    if let Command::Copyedit {
        paths,
        dialect,
        allow_word,
    } = &cli.command
    {
        return copyedit::run(
            paths,
            dialect.as_str(),
            allow_word.as_slice(),
            cli.format,
            &resolved.settings,
            cli.markdown,
            &engine,
            &models,
        );
    }
    let scan = matches!(cli.command, Command::Scan { .. });
    let lint = matches!(cli.command, Command::Lint { .. });
    let mut reports = vec![];
    let mut errors = vec![];
    match cli.command {
        Command::Detect { path } | Command::Analyze { path } => {
            match load(&path, resolved.settings.max_bytes).and_then(|input| {
                let side_text = (resolved.settings.gptzero || resolved.settings.openrouter_judge)
                    .then(|| input.text.clone());
                let mut report = engine.analyze_with_models(
                    input.text,
                    cli.markdown || nobotrs::document::Document::is_markdown(Path::new(&path)),
                    &path,
                    &resolved.settings,
                    &models,
                )?;
                if input.truncated {
                    report.mark_input_truncated();
                }
                if let Some(text) = side_text {
                    if resolved.settings.gptzero {
                        let key = std::env::var("GPTZERO_API_KEY").ok();
                        report.external = Some(nobotrs::external::gptzero::compare(
                            &resolved.settings,
                            &text,
                            key.as_deref(),
                        ));
                    }
                    if resolved.settings.openrouter_judge {
                        let key = std::env::var("OPENROUTER_API_KEY").ok();
                        report.openrouter = Some(nobotrs::external::openrouter::judge(
                            &resolved.settings,
                            &text,
                            key.as_deref(),
                        ));
                    }
                }
                Ok(report)
            }) {
                Ok(r) => reports.push(r),
                Err(e) => errors.push(serde_json::json!({"path":path,"error":e,"complete":false})),
            }
        }
        Command::Lint { paths } => {
            for path in paths {
                match load(&path, resolved.settings.max_bytes).and_then(|input| {
                    let mut report = engine.analyze_with_models(
                        input.text,
                        cli.markdown || nobotrs::document::Document::is_markdown(Path::new(&path)),
                        &path,
                        &resolved.settings,
                        &models,
                    )?;
                    if input.truncated {
                        report.mark_input_truncated();
                    }
                    Ok(report)
                }) {
                    Ok(report) => reports.push(report),
                    Err(error) => {
                        errors.push(serde_json::json!({"path":path,"error":error,"complete":false}))
                    }
                }
            }
        }
        Command::Scan { dir } => {
            if !dir.is_dir() {
                return Err(format!("{} is not a directory", dir.display()));
            }
            if dir
                .symlink_metadata()
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink()
            {
                return Err("scan root must not be a symlink".into());
            }
            let mut paths = vec![];
            for entry in walkdir::WalkDir::new(&dir)
                .follow_links(false)
                .sort_by_file_name()
                .into_iter()
                .filter_entry(|e| {
                    e.depth() == 0
                        || !e.file_type().is_dir()
                        || !matches!(
                            e.file_name().to_str(),
                            Some(".git" | "target" | "node_modules" | "vendor" | ".venv" | "venv")
                        )
                })
            {
                match entry {
                    Ok(e) if e.file_type().is_file() && e.path().extension().and_then(|s|s.to_str()).is_some_and(|s|matches!(s.to_ascii_lowercase().as_str(),"md"|"markdown"|"txt"))=>paths.push(e.into_path()),
                    Ok(_)=>{},
                    Err(e)=>errors.push(serde_json::json!({"path":e.path().map(|p|p.display().to_string()),"error":e.to_string(),"complete":false})),
                }
            }
            paths.sort();
            for path in paths {
                let name = path.to_str().ok_or("scan path is not UTF-8")?;
                match load(name, resolved.settings.max_bytes).and_then(|input| {
                    let mut report = engine.analyze_with_models(
                        input.text,
                        cli.markdown || nobotrs::document::Document::is_markdown(&path),
                        name,
                        &resolved.settings,
                        &models,
                    )?;
                    if input.truncated {
                        report.mark_input_truncated();
                    }
                    Ok(report)
                }) {
                    Ok(report) => reports.push(report),
                    Err(e) => {
                        errors.push(serde_json::json!({"path":name,"error":e,"complete":false}))
                    }
                }
            }
        }
        Command::Review { .. }
        | Command::Compare { .. }
        | Command::Copyedit { .. }
        | Command::Facts { .. }
        | Command::Config
        | Command::Guide
        | Command::AiWritingGuide => unreachable!(),
    }
    let code = if !errors.is_empty() {
        2
    } else {
        batch_code(&reports, lint)
    };
    for e in &errors {
        eprintln!("nobotrs: {}: {}", e["path"], e["error"]);
    }
    match cli.format {
        Format::Json => {
            let value = if reports.len() == 1 && errors.is_empty() && !scan {
                serde_json::to_value(&reports[0]).map_err(|e| e.to_string())?
            } else {
                serde_json::json!({"schema_version":"1.0.0","reports":reports,"errors":errors,"exit_code":code})
            };
            emit(&serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?)?;
        }
        Format::Human => {
            for r in &reports {
                emit(&nobotrs::output::human(r))?;
            }
            if reports.is_empty() && errors.is_empty() {
                emit("No supported files found; inconclusive")?;
            }
        }
        Format::Sarif => {
            let mut value = nobotrs::output::sarif(&reports);
            if !errors.is_empty() {
                value["runs"][0]["invocations"][0]["executionSuccessful"] =
                    serde_json::json!(false);
                let notes = value["runs"][0]["invocations"][0]["toolExecutionNotifications"]
                    .as_array_mut()
                    .ok_or("SARIF notification construction failed")?;
                for e in errors {
                    notes.push(
                        serde_json::json!({"level":"error","message":{"text":e.to_string()}}),
                    );
                }
            }
            emit(&serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?)?;
        }
    }
    Ok(code)
}
fn batch_code(reports: &[Report], lint: bool) -> i32 {
    let statuses: Vec<_> = reports.iter().map(|r| r.exit_code(lint)).collect();
    if statuses.contains(&2) {
        2
    } else if statuses.contains(&1) {
        1
    } else if statuses.is_empty() || statuses.contains(&3) {
        3
    } else {
        0
    }
}
fn load(path: &str, limit: usize) -> Result<ReadInput, String> {
    if path == "-" {
        read_bounded(io::stdin().lock(), limit)
    } else {
        read_bounded(
            std::fs::File::open(path).map_err(|e| format!("{path}: {e}"))?,
            limit,
        )
    }
}
fn emit(text: &str) -> Result<(), String> {
    let mut stdout = io::stdout().lock();
    writeln!(stdout, "{text}").map_err(|e| format!("stdout: {e}"))
}
