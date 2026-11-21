use super::{
    abstain, model_score, DetectorScopeEvidence, FeatureContribution, FeatureHighlight, Manifest,
    ModelEvidence, MODEL_FAMILY,
};
use crate::{
    availability::Availability,
    backend::{DetectorBackend, ScoreOutcome},
    deadline::Deadline,
    document::Document,
    error::Error,
    score::Score,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::{BufRead, BufReader, Read, Write},
    ops::Range,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        mpsc::{self, Receiver, RecvTimeoutError},
        Mutex,
    },
    time::{Duration, Instant},
};
use tokenizers::Tokenizer;

const PROTOCOL: &str = "nobotrs-detectorscope-v1";
const WORKER: &str = include_str!("../../integrations/model_workers/detectorscope_worker.py");
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(180);
const REQUEST_TIMEOUT: Duration = Duration::from_secs(180);
const MAX_LINE: usize = 8 * 1024 * 1024;

pub struct DetectorScopeBackend {
    manifest: &'static Manifest,
    root: PathBuf,
    tokenizer: Mutex<Option<std::sync::Arc<Tokenizer>>>,
    verified: Mutex<bool>,
    worker: Mutex<WorkerState>,
}

enum WorkerState {
    Empty,
    Ready(Box<WorkerClient>),
}

#[derive(Debug, Deserialize)]
struct Handshake {
    #[serde(rename = "type")]
    kind: String,
    protocol: String,
    model_revision: String,
    code_revision: String,
    head: String,
    tau: f64,
    device: String,
    dtype: String,
    threshold: f64,
}

#[derive(Debug, Serialize)]
struct Request<'a> {
    id: u64,
    text: &'a str,
    head: &'a str,
    tau: f64,
}

#[derive(Debug, Deserialize)]
struct Response {
    id: u64,
    ok: bool,
    #[serde(default)]
    error: Option<String>,
    logit: Option<f64>,
    bias: Option<f64>,
    threshold: Option<f64>,
    reconstruction_residual: Option<f64>,
    active_features: Option<usize>,
    omitted_features: Option<usize>,
    all_contribution_sum: Option<f64>,
    displayed_contribution_sum: Option<f64>,
    remainder: Option<f64>,
    tokens: Option<usize>,
    features: Option<Vec<WorkerFeature>>,
}

struct SuccessResponse {
    logit: f64,
    bias: f64,
    threshold: f64,
    reconstruction_residual: f64,
    active_features: usize,
    omitted_features: usize,
    remainder: f64,
    tokens: usize,
    features: Vec<WorkerFeature>,
}

#[derive(Debug, Deserialize)]
struct WorkerFeature {
    id: usize,
    description: String,
    contribution: f64,
    #[serde(default)]
    highlights: Vec<WorkerHighlight>,
}

#[derive(Debug, Deserialize)]
struct WorkerHighlight {
    token_index: usize,
    text: String,
    activation: f64,
    start: usize,
    end: usize,
}

impl DetectorScopeBackend {
    pub fn new(manifest: &'static Manifest, root: &Path) -> Result<Self, String> {
        Ok(Self {
            manifest,
            root: root.to_path_buf(),
            tokenizer: Mutex::new(None),
            verified: Mutex::new(false),
            worker: Mutex::new(WorkerState::Empty),
        })
    }

    fn request(
        &self,
        text: &str,
        deadline: Deadline,
    ) -> Result<(SuccessResponse, String, String), Error> {
        let mut state = self
            .worker
            .lock()
            .map_err(|_| Error::InternalError("worker lock poisoned".into()))?;
        if matches!(&*state, WorkerState::Empty) {
            let worker = WorkerClient::start(self.manifest, &self.root, deadline)?;
            *state = WorkerState::Ready(Box::new(worker));
        }
        let result = match &mut *state {
            WorkerState::Ready(worker) => worker
                .request(text, deadline)
                .map(|response| (response, worker.device.clone(), worker.dtype.clone())),
            WorkerState::Empty => unreachable!(),
        };
        if result.is_err() {
            // Drop (kill + reap) the failed worker so a later request can restart cleanly.
            *state = WorkerState::Empty;
        }
        result
    }

    fn tokenizer(&self) -> Result<std::sync::Arc<Tokenizer>, Error> {
        let mut slot = self
            .tokenizer
            .lock()
            .map_err(|_| Error::InternalError("tokenizer lock poisoned".into()))?;
        if let Some(tokenizer) = slot.as_ref() {
            return Ok(tokenizer.clone());
        }
        let pin =
            self.manifest.tokenizer.as_ref().ok_or_else(|| {
                Error::ModelLoadFailed("DetectorScope tokenizer pin missing".into())
            })?;
        let path = self.root.join(&pin.file);
        let bytes = crate::models::read_verified(&path, &pin.sha256)?;
        let tokenizer = Tokenizer::from_bytes(bytes)
            .map_err(|e| Error::ModelLoadFailed(format!("tokenizer: {e}")))?;
        let tokenizer = std::sync::Arc::new(tokenizer);
        *slot = Some(tokenizer.clone());
        Ok(tokenizer)
    }
}

impl DetectorBackend for DetectorScopeBackend {
    fn name(&self) -> &str {
        &self.manifest.id
    }
    fn family(&self) -> crate::backend::SignalFamily {
        MODEL_FAMILY
    }
    fn availability(&self) -> Availability {
        Availability::Ready
    }

    fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome {
        if !doc.english_supported() {
            let unknown = doc.language.applicability == "unknown";
            return abstain(
                &self.manifest.id,
                if unknown {
                    super::ModelAbstentionCode::LanguageUnknown
                } else {
                    super::ModelAbstentionCode::LanguageUnsupported
                },
                if unknown {
                    "assert --language en before using local model evidence"
                } else {
                    "the initial model profiles require English"
                },
                doc.words.len(),
                None,
            );
        }
        let minimum = self.manifest.minimum_words.unwrap_or(25);
        if doc.words.len() < minimum {
            return abstain(
                &self.manifest.id,
                super::ModelAbstentionCode::TextTooShort,
                &format!(
                    "{} prepared words; the profile requires at least {}",
                    doc.words.len(),
                    minimum
                ),
                doc.words.len(),
                Some(minimum),
            );
        }
        if deadline.expired() {
            return ScoreOutcome::Failed(Error::Timeout);
        }
        let started = Instant::now();
        let verified = match self.verified.lock() {
            Ok(mut verified) => {
                if *verified {
                    true
                } else {
                    match verify_all(self.manifest, &self.root) {
                        Ok(()) => {
                            *verified = true;
                            true
                        }
                        Err(error) => return ScoreOutcome::Failed(error),
                    }
                }
            }
            Err(_) => return ScoreOutcome::Failed(Error::InternalError("verify lock".into())),
        };
        let _ = verified;
        let tokenizer = match self.tokenizer() {
            Ok(tokenizer) => tokenizer,
            Err(error) => return ScoreOutcome::Failed(error),
        };
        let (flat, mapping) = flatten_with_map(&doc.prose);
        let excerpt = match detector_excerpt(&tokenizer, &flat, self.manifest.max_tokens) {
            Ok(excerpt) => excerpt,
            Err(error) => return ScoreOutcome::Failed(error),
        };
        let prepared_chars = doc.prose.chars().count();
        let prose_end = mapping
            .get(excerpt.bytes.saturating_sub(1))
            .map(|range| range.end)
            .unwrap_or(doc.prose.len())
            .min(doc.prose.len());
        let excerpt_chars = doc.prose[..prose_end].chars().count();
        let coverage = if prepared_chars == 0 {
            None
        } else {
            Some(excerpt_chars as f64 / prepared_chars as f64)
        };
        let planned = super::PlannedExcerpt {
            prepared_bytes: doc.prose.len(),
            prepared_words: doc.words.len(),
            excerpt_bytes: prose_end,
            excerpt_tokens: excerpt.tokens,
            token_limit: self.manifest.max_tokens,
            truncated: excerpt.truncated,
            coverage,
        };
        let fail = |error: Error| {
            ScoreOutcome::Failed(super::model_failure(
                error.to_string(),
                Some(planned.clone()),
            ))
        };
        let (response, worker_device, worker_dtype) =
            match self.request(&flat[..excerpt.bytes], deadline) {
                Ok(value) => value,
                Err(error) => return fail(error),
            };
        if deadline.expired() {
            return fail(Error::Timeout);
        }
        if response.tokens != excerpt.tokens {
            return fail(Error::ModelLoadFailed(format!(
                "DetectorScope worker scored {} tokens, expected {} for the bounded excerpt",
                response.tokens, excerpt.tokens
            )));
        }
        let head = self.manifest.head.as_ref();
        let feature_filter = head.map(|h| h.feature_filter).unwrap_or(0.85);
        let mut top_features = vec![];
        for feature in response.features {
            let mut highlights = vec![];
            for highlight in feature.highlights {
                let prose = flat_range_to_prose(&mapping, highlight.start..highlight.end);
                let source_ranges = prose
                    .as_ref()
                    .map(|range| doc.source_ranges(range.clone()))
                    .unwrap_or_default();
                if source_ranges.is_empty() {
                    continue;
                }
                highlights.push(FeatureHighlight {
                    token_index: highlight.token_index,
                    text: highlight.text,
                    activation: highlight.activation,
                    prose_ranges: prose.into_iter().collect(),
                    source_ranges,
                });
            }
            top_features.push(FeatureContribution {
                id: feature.id,
                description: feature.description,
                contribution: feature.contribution,
                highlights,
            });
        }
        let threshold = if response.threshold > 0.0 {
            response.threshold
        } else {
            head.map(|h| h.threshold).unwrap_or(0.5008)
        };
        let evidence = ModelEvidence {
            backend: self.manifest.id.clone(),
            model_revision: self.manifest.upstream.revision.clone(),
            tokenizer_revision: self
                .manifest
                .tokenizer
                .as_ref()
                .map(|t| t.revision.clone())
                .unwrap_or_default(),
            code_revision: self.manifest.code.as_ref().map(|c| c.revision.clone()),
            runtime: "detectorscope-worker".into(),
            device: worker_device,
            precision: worker_dtype,
            preprocessing_revision: self.manifest.preprocessing_revision.clone(),
            raw_output: response.logit,
            raw_units: "logit (higher = machine-like at the released head threshold)".into(),
            threshold: Some(threshold),
            threshold_source: Some("released logreg head threshold".into()),
            prepared_bytes: doc.prose.len(),
            prepared_words: doc.words.len(),
            excerpt_bytes: prose_end,
            excerpt_tokens: excerpt.tokens,
            token_limit: self.manifest.max_tokens,
            truncated: excerpt.truncated,
            planned_coverage: coverage,
            execution_coverage: coverage,
            excerpt_coverage: coverage,
            elapsed_ms: started.elapsed().as_secs_f64() * 1000.0,
            detectorscope: Some(DetectorScopeEvidence {
                bias: response.bias,
                reconstruction_residual: response.reconstruction_residual,
                active_features: response.active_features,
                feature_filter,
                formatting_profile: "flat-whitespace-v1".into(),
                top_features,
                omitted_features: response.omitted_features,
                remainder: response.remainder,
            }),
        };
        let mut score: Score = model_score(&self.manifest.id);
        score.model_evidence = Some(evidence);
        score.metrics.insert(
            "model_score".into(),
            crate::score::Metric {
                value: response.logit,
                unit: "logit".into(),
                method: self.manifest.preprocessing_revision.clone(),
            },
        );
        score.metrics.insert(
            "model_threshold".into(),
            crate::score::Metric {
                value: threshold,
                unit: "logit".into(),
                method: "released logreg head".into(),
            },
        );
        ScoreOutcome::Scored(score)
    }
}

fn verify_all(manifest: &Manifest, root: &Path) -> Result<(), Error> {
    for artifact in &manifest.artifacts {
        verify_streaming(&root.join(&artifact.path), &artifact.sha256)?;
    }
    if let Some(tokenizer) = &manifest.tokenizer {
        verify_streaming(&root.join(&tokenizer.file), &tokenizer.sha256)?;
    }
    Ok(())
}

fn verify_streaming(path: &Path, expected: &str) -> Result<(), Error> {
    let mut file =
        File::open(path).map_err(|e| Error::ModelLoadFailed(format!("{}: {e}", path.display())))?;
    let mut hasher = Sha256::new();
    let mut buffer = vec![0u8; 1 << 20];
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|e| Error::ModelLoadFailed(format!("{}: {e}", path.display())))?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    if format!("{:x}", hasher.finalize()) != expected {
        return Err(Error::ChecksumMismatch);
    }
    Ok(())
}

struct Excerpt {
    bytes: usize,
    tokens: usize,
    truncated: bool,
}

fn detector_excerpt(
    tokenizer: &Tokenizer,
    text: &str,
    max_tokens: usize,
) -> Result<Excerpt, Error> {
    // tokenizer.json can carry its own truncation defaults; length must be measured
    // on an explicitly unbounded clone, then the retained offsets drive clipping.
    let mut full_tokenizer = tokenizer.clone();
    full_tokenizer
        .with_truncation(None)
        .map_err(|e| Error::InternalError(format!("tokenizer truncation: {e}")))?;
    full_tokenizer.with_padding(None);
    let full = full_tokenizer
        .encode(text, true)
        .map_err(|e| Error::InternalError(format!("tokenizer: {e}")))?;
    let total = full.get_ids().len();
    if total <= max_tokens {
        return Ok(Excerpt {
            bytes: text.len(),
            tokens: total,
            truncated: false,
        });
    }
    let end = (0..max_tokens)
        .rev()
        .find_map(|index| {
            full.get_offsets()
                .get(index)
                .filter(|(start, end)| start < end)
                .map(|(_, end)| *end)
        })
        .unwrap_or(text.len())
        .min(text.len());
    Ok(Excerpt {
        bytes: floor_char_boundary(text, end),
        tokens: max_tokens,
        truncated: true,
    })
}

fn source_revision(source: &Path) -> Result<String, Error> {
    let head = std::fs::read_to_string(source.join(".git/HEAD"))
        .map_err(|e| Error::ModelLoadFailed(format!("source .git/HEAD: {e}")))?;
    let head = head.trim();
    if let Some(reference) = head.strip_prefix("ref: ") {
        if let Ok(value) = std::fs::read_to_string(source.join(".git").join(reference)) {
            return Ok(value.trim().to_string());
        }
        let packed = std::fs::read_to_string(source.join(".git/packed-refs"))
            .map_err(|e| Error::ModelLoadFailed(format!("source packed-refs: {e}")))?;
        for line in packed.lines() {
            if let Some((revision, name)) = line.split_once(' ') {
                if name.trim() == reference {
                    return Ok(revision.to_string());
                }
            }
        }
        return Err(Error::ModelLoadFailed(format!(
            "source reference {reference} not found"
        )));
    }
    Ok(head.to_string())
}

struct WorkerClient {
    child: Child,
    writer: mpsc::SyncSender<Vec<u8>>,
    lines: Receiver<String>,
    device: String,
    dtype: String,
    next_id: u64,
}

impl WorkerClient {
    fn start(manifest: &Manifest, root: &Path, deadline: Deadline) -> Result<Self, Error> {
        let python = std::env::var_os("NOBOTRS_MODEL_PYTHON")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("python3"));
        let source = std::env::var_os("NOBOTRS_DETECTORSCOPE_SOURCE")
            .map(PathBuf::from)
            .unwrap_or_else(|| root.join("detectorscope/source"));
        if !source.is_dir() {
            return Err(Error::ModelLoadFailed(format!(
                "DetectorScope source checkout not found at {}; set NOBOTRS_DETECTORSCOPE_SOURCE",
                source.display()
            )));
        }
        let expected_code = manifest
            .code
            .as_ref()
            .map(|code| code.revision.as_str())
            .unwrap_or("");
        let actual_code = source_revision(&source)?;
        if actual_code != expected_code {
            return Err(Error::ModelLoadFailed(format!(
                "DetectorScope source revision mismatch: expected {expected_code}, found {actual_code}"
            )));
        }
        let device = std::env::var("NOBOTRS_DETECTORSCOPE_DEVICE").unwrap_or_else(|_| "cpu".into());
        let dtype =
            std::env::var("NOBOTRS_DETECTORSCOPE_DTYPE").unwrap_or_else(|_| "float32".into());
        let mut child = Command::new(&python)
            .arg("-c")
            .arg(WORKER)
            .env("NOBOTRS_DETECTORSCOPE_SOURCE", &source)
            .env("NOBOTRS_MODELS_DIR", root)
            .env("NOBOTRS_DETECTORSCOPE_DEVICE", &device)
            .env("NOBOTRS_DETECTORSCOPE_DTYPE", &dtype)
            .env("HF_HUB_OFFLINE", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| Error::ModelLoadFailed(format!("starting {}: {e}", python.display())))?;
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| Error::InternalError("worker stdin unavailable".into()))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| Error::InternalError("worker stdout unavailable".into()))?;
        if let Some(stderr) = child.stderr.take() {
            std::thread::spawn(move || {
                for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                    eprintln!("detectorscope: {line}");
                }
            });
        }
        let (writer, requests) = mpsc::sync_channel::<Vec<u8>>(1);
        std::thread::spawn(move || {
            while let Ok(frame) = requests.recv() {
                if stdin.write_all(&frame).and_then(|_| stdin.flush()).is_err() {
                    break;
                }
            }
        });
        let (sender, lines) = mpsc::sync_channel(8);
        std::thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let mut buf = Vec::new();
            loop {
                buf.clear();
                match reader
                    .by_ref()
                    .take(MAX_LINE as u64 + 1)
                    .read_until(b'\n', &mut buf)
                {
                    Ok(0) | Err(_) => break,
                    Ok(_) if buf.len() > MAX_LINE || !buf.ends_with(b"\n") => break,
                    Ok(_) => {
                        if sender
                            .send(String::from_utf8_lossy(&buf).trim().to_string())
                            .is_err()
                        {
                            break;
                        }
                    }
                }
            }
        });
        let budget = HANDSHAKE_TIMEOUT.min(deadline.remaining());
        let line = match lines.recv_timeout(budget) {
            Ok(line) => line,
            Err(RecvTimeoutError::Timeout) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(Error::ModelLoadFailed(
                    "DetectorScope worker handshake timed out".into(),
                ));
            }
            Err(RecvTimeoutError::Disconnected) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(Error::ModelLoadFailed(
                    "DetectorScope worker exited before its handshake; check stderr diagnostics"
                        .into(),
                ));
            }
        };
        let value: serde_json::Value = match serde_json::from_str(&line) {
            Ok(value) => value,
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(Error::ModelLoadFailed(format!(
                    "worker handshake: {error}: {line}"
                )));
            }
        };
        if value.get("type").and_then(|kind| kind.as_str()) == Some("error") {
            let detail = value
                .get("error")
                .and_then(|error| error.as_str())
                .unwrap_or("unspecified startup error");
            let _ = child.kill();
            let _ = child.wait();
            return Err(Error::ModelLoadFailed(format!(
                "DetectorScope worker startup failed: {detail}"
            )));
        }
        let handshake: Handshake = match serde_json::from_value(value) {
            Ok(handshake) => handshake,
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(Error::ModelLoadFailed(format!(
                    "worker handshake: {error}: {line}"
                )));
            }
        };
        if handshake.kind != "ready"
            || handshake.protocol != PROTOCOL
            || handshake.model_revision != manifest.upstream.revision
            || handshake.code_revision != expected_code
            || handshake.head != "logreg"
            || (handshake.tau - 0.85).abs() > 1e-9
            || handshake.device != device
            || handshake.dtype != dtype
            || (handshake.threshold
                - manifest
                    .head
                    .as_ref()
                    .map(|h| h.threshold)
                    .unwrap_or(0.5008))
            .abs()
                > 1e-6
        {
            let _ = child.kill();
            let _ = child.wait();
            return Err(Error::ModelLoadFailed(
                "DetectorScope worker handshake identity mismatch".into(),
            ));
        }
        Ok(Self {
            child,
            writer,
            lines,
            device: handshake.device,
            dtype: handshake.dtype,
            next_id: 1,
        })
    }

    fn request(&mut self, text: &str, deadline: Deadline) -> Result<SuccessResponse, Error> {
        let id = self.next_id;
        self.next_id += 1;
        let request = Request {
            id,
            text,
            head: "logreg",
            tau: 0.85,
        };
        let mut line = serde_json::to_vec(&request)
            .map_err(|e| Error::InternalError(format!("request: {e}")))?;
        line.push(b'\n');
        if line.len() > MAX_LINE {
            return Err(Error::ModelLoadFailed(
                "DetectorScope request frame exceeds the bounded protocol limit".into(),
            ));
        }
        if self.writer.try_send(line).is_err() {
            let _ = self.child.kill();
            let _ = self.child.wait();
            return Err(Error::ModelLoadFailed(
                "DetectorScope worker is not consuming requests".into(),
            ));
        }
        let budget = REQUEST_TIMEOUT.min(deadline.remaining());
        let line = match self.lines.recv_timeout(budget) {
            Ok(line) => line,
            Err(RecvTimeoutError::Timeout) => {
                let _ = self.child.kill();
                let _ = self.child.wait();
                return Err(Error::Timeout);
            }
            Err(RecvTimeoutError::Disconnected) => {
                let _ = self.child.kill();
                let _ = self.child.wait();
                return Err(Error::ModelLoadFailed("DetectorScope worker exited".into()));
            }
        };
        let response: Response = serde_json::from_str(&line)
            .map_err(|e| Error::InternalError(format!("worker response: {e}: {line}")))?;
        if response.id != id {
            return Err(Error::InternalError(format!(
                "worker request id mismatch: expected {id}, got {}",
                response.id
            )));
        }
        if !response.ok {
            return Err(Error::ModelLoadFailed(
                response
                    .error
                    .unwrap_or_else(|| "DetectorScope worker rejected request".into()),
            ));
        }
        let (
            Some(logit),
            Some(bias),
            Some(threshold),
            Some(reconstruction_residual),
            Some(active_features),
            Some(omitted_features),
            Some(all_contribution_sum),
            Some(displayed_contribution_sum),
            Some(remainder),
            Some(tokens),
            Some(features),
        ) = (
            response.logit,
            response.bias,
            response.threshold,
            response.reconstruction_residual,
            response.active_features,
            response.omitted_features,
            response.all_contribution_sum,
            response.displayed_contribution_sum,
            response.remainder,
            response.tokens,
            response.features,
        )
        else {
            return Err(Error::ModelLoadFailed(
                "DetectorScope worker success response omitted evidence fields".into(),
            ));
        };
        if !logit.is_finite()
            || !bias.is_finite()
            || !threshold.is_finite()
            || !all_contribution_sum.is_finite()
            || !displayed_contribution_sum.is_finite()
            || !reconstruction_residual.is_finite()
            || !remainder.is_finite()
            || features.len() > active_features
            || omitted_features != active_features - features.len()
        {
            return Err(Error::ModelLoadFailed(
                "DetectorScope worker returned invalid or incomplete evidence".into(),
            ));
        }
        let displayed_remainder = logit - bias - displayed_contribution_sum;
        if (displayed_remainder - remainder).abs() > 1e-3 {
            return Err(Error::ModelLoadFailed(
                "DetectorScope displayed remainder does not match the signed contributions".into(),
            ));
        }
        let reconstructed = logit - bias - all_contribution_sum;
        if reconstructed.abs() > 1e-3 || reconstruction_residual.abs() > 1e-3 {
            return Err(Error::ModelLoadFailed(format!(
                "DetectorScope additive reconstruction failed: residual {:.6}, signed sum {:.6}",
                reconstructed, all_contribution_sum
            )));
        }
        Ok(SuccessResponse {
            logit,
            bias,
            threshold,
            reconstruction_residual,
            active_features,
            omitted_features,
            remainder,
            tokens,
            features,
        })
    }
}

impl Drop for WorkerClient {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn flatten_with_map(text: &str) -> (String, Vec<Range<usize>>) {
    let mut flat = String::with_capacity(text.len());
    let mut mapping: Vec<Range<usize>> = Vec::with_capacity(text.len());
    let mut last_end = None;
    for word in text.split_whitespace() {
        let start = word.as_ptr() as usize - text.as_ptr() as usize;
        let end = start + word.len();
        if let Some(previous) = last_end {
            if start > previous {
                flat.push(' ');
                mapping.push(previous..start);
            }
        }
        for (offset, c) in word.char_indices() {
            flat.push(c);
            for _ in 0..c.len_utf8() {
                mapping.push(start + offset..start + offset + c.len_utf8());
            }
        }
        last_end = Some(end);
    }
    (flat, mapping)
}

fn flat_range_to_prose(mapping: &[Range<usize>], range: Range<usize>) -> Option<Range<usize>> {
    if range.start >= range.end || range.end > mapping.len() {
        return None;
    }
    let first = &mapping[range.start];
    let last = &mapping[range.end - 1];
    (!first.is_empty() && !last.is_empty()).then_some(first.start..last.end)
}

fn floor_char_boundary(text: &str, mut end: usize) -> usize {
    end = end.min(text.len());
    while end > 0 && !text.is_char_boundary(end) {
        end -= 1;
    }
    end
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flattening_preserves_word_content_and_maps_back() {
        let text = "One\n\ttwo   three";
        let (flat, map) = flatten_with_map(text);
        assert_eq!(flat, "One two three");
        assert_eq!(flat_range_to_prose(&map, 0..3), Some(0..3));
        assert_eq!(flat_range_to_prose(&map, 4..7), Some(5..8));
        assert_eq!(flat_range_to_prose(&map, 8..13), Some(11..16));
    }

    #[test]
    fn unicode_flattening_has_byte_accurate_ranges() {
        let text = "é  — 中";
        let (flat, map) = flatten_with_map(text);
        assert_eq!(flat, "é — 中");
        assert_eq!(flat_range_to_prose(&map, 0..2), Some(0..2));
        assert_eq!(flat_range_to_prose(&map, 3..6), Some(4..7));
        assert_eq!(flat_range_to_prose(&map, 7..10), Some(8..11));
    }
}
