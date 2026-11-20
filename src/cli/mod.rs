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
    /// Analyze a file or stdin (-) using a quorum of independent heuristic families.
    Detect { path: String },
    /// Report individual editing findings, independent of detection quorum.
    Lint {
        #[arg(required = true)]
        paths: Vec<String>,
    },
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
    let resolved = ResolvedConfig::load(
        cli.config,
        Overrides {
            minimum_severity: cli.minimum_severity,
            quorum: cli.quorum,
            max_bytes: cli.max_bytes,
            max_candidates: cli.max_candidates,
            display_limit: cli.display_limit,
            timeout_ms: cli.timeout_ms,
            language: cli.language,
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
        let value = serde_json::json!({"schema_version":"1.0.0","configuration":resolved,"backends":nobotrs::config::BACKENDS.iter().map(|name|serde_json::json!({"backend":name,"availability":"ready","enabled":resolved.settings.enabled_backends.iter().any(|n|n==name)})).collect::<Vec<_>>()});
        emit(&serde_json::to_string_pretty(&value).map_err(|e| e.to_string())?)?;
        return Ok(0);
    }
    if matches!(cli.command, Command::Guide) {
        match cli.format {
            Format::Human=>emit(include_str!("../../docs/writing-guide.md"))?,
            Format::Json=>emit(&serde_json::json!({"schema_version":"1.0.0","guide":include_str!("../../docs/writing-guide.md")}).to_string())?,
            Format::Sarif=>return Err("guide does not produce SARIF".into()),
        }
        return Ok(0);
    }
    let scan = matches!(cli.command, Command::Scan { .. });
    let lint = matches!(cli.command, Command::Lint { .. });
    let mut reports = vec![];
    let mut errors = vec![];
    match cli.command {
        Command::Detect { path } | Command::Analyze { path } => {
            match load(&path, resolved.settings.max_bytes).and_then(|input| {
                let mut report = engine.analyze(
                    input.text,
                    cli.markdown || nobotrs::document::Document::is_markdown(Path::new(&path)),
                    &path,
                    &resolved.settings,
                )?;
                if input.truncated {
                    report.mark_input_truncated();
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
                    let mut report = engine.analyze(
                        input.text,
                        cli.markdown || nobotrs::document::Document::is_markdown(Path::new(&path)),
                        &path,
                        &resolved.settings,
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
                    let mut report = engine.analyze(
                        input.text,
                        cli.markdown || nobotrs::document::Document::is_markdown(&path),
                        name,
                        &resolved.settings,
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
        Command::Config | Command::Guide | Command::AiWritingGuide => unreachable!(),
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
