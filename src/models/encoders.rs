use super::{abstain, model_score, Manifest, ModelEvidence, MODEL_FAMILY};
use crate::{
    availability::Availability,
    backend::{DetectorBackend, ScoreOutcome},
    deadline::Deadline,
    document::Document,
    error::Error,
    score::Score,
};
use candle_core::{DType, Device, Tensor, D};
use candle_nn::{Linear, Module};
use candle_transformers::models::debertav2::{Config, DebertaV2Model};
use std::{
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::Instant,
};
use tokenizers::Tokenizer;

const DEVICE: &str = "cpu";
const PRECISION: &str = "float32";

pub struct EncoderBackend {
    manifest: &'static Manifest,
    root: PathBuf,
    session: LazySession,
}

enum LazyState {
    Empty,
    Failed(Error),
    Ready(Arc<Session>),
}

struct LazySession {
    state: Mutex<LazyState>,
}

impl LazySession {
    fn new() -> Self {
        Self {
            state: Mutex::new(LazyState::Empty),
        }
    }

    fn get(&self, manifest: &'static Manifest, root: &Path) -> Result<Arc<Session>, Error> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| Error::InternalError("model session lock poisoned".into()))?;
        match &*state {
            LazyState::Ready(session) => return Ok(session.clone()),
            LazyState::Failed(error) => return Err(error.clone()),
            LazyState::Empty => {}
        }
        match Session::load(manifest, root) {
            Ok(session) => {
                let session = Arc::new(session);
                *state = LazyState::Ready(session.clone());
                Ok(session)
            }
            Err(error) => {
                *state = LazyState::Failed(error.clone());
                Err(error)
            }
        }
    }
}

struct Session {
    model: DebertaV2Model,
    classifier: Classifier,
    tokenizer: Tokenizer,
    max_tokens: usize,
}

enum Classifier {
    /// Desklib: masked-mean pooled hidden state -> one linear logit.
    Desklib(Linear),
    /// ConPara: CLS -> Linear(1024,512) -> GELU -> Linear(512,2), margin = AI - human.
    ConPara { first: Linear, second: Linear },
}

impl EncoderBackend {
    pub fn new(manifest: &'static Manifest, root: &Path) -> Result<Self, String> {
        Ok(Self {
            manifest,
            root: root.to_path_buf(),
            session: LazySession::new(),
        })
    }
}

impl DetectorBackend for EncoderBackend {
    fn name(&self) -> &str {
        &self.manifest.id
    }

    fn family(&self) -> crate::backend::SignalFamily {
        MODEL_FAMILY
    }

    fn availability(&self) -> Availability {
        Availability::Ready
    }

    fn score_full(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome {
        let opening = self.score(doc, deadline);
        let ScoreOutcome::Scored(score) = opening else {
            return opening;
        };
        let session = match self.session.get(self.manifest, &self.root) {
            Ok(session) => session,
            Err(error) => return super::full::planning_failure(score, doc, error),
        };
        let (text, mapping) = if self.manifest.id == "conpara" {
            super::normalize_input_with_map(&doc.prose)
        } else {
            (doc.prose.clone(), super::full::identity_map(&doc.prose))
        };
        let windows = match super::full::plan(
            doc,
            &session.tokenizer,
            &text,
            &mapping,
            session.max_tokens,
            deadline,
        ) {
            Ok(windows) => windows,
            Err(error) => return super::full::planning_failure(score, doc, error),
        };
        let run = super::windows::run_windows(&windows, deadline, |ids| session.infer(ids));
        super::full::finish(score, doc, &mapping, &windows, run, vec![])
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
        if doc.words.len() < self.manifest_minimum_words() {
            return abstain(
                &self.manifest.id,
                super::ModelAbstentionCode::TextTooShort,
                &format!(
                    "{} prepared words; the profile requires at least {}",
                    doc.words.len(),
                    self.manifest_minimum_words()
                ),
                doc.words.len(),
                Some(self.manifest_minimum_words()),
            );
        }
        if deadline.expired() {
            return ScoreOutcome::Failed(Error::Timeout);
        }
        let started = Instant::now();
        let session = match self.session.get(self.manifest, &self.root) {
            Ok(session) => session,
            Err(error) => return ScoreOutcome::Failed(error),
        };
        let prepared = if self.manifest.id == "conpara" {
            super::normalize_input(&doc.prose)
        } else {
            doc.prose.clone()
        };
        let excerpt = match build_excerpt(&session.tokenizer, session.max_tokens, &prepared) {
            Ok(excerpt) => excerpt,
            Err(error) => return ScoreOutcome::Failed(error),
        };
        let planned = super::PlannedExcerpt {
            prepared_bytes: prepared.len(),
            prepared_words: doc.words.len(),
            excerpt_bytes: excerpt.bytes,
            excerpt_tokens: excerpt.tokens,
            token_limit: session.max_tokens,
            truncated: excerpt.truncated,
            coverage: excerpt.coverage,
        };
        let fail = |error: Error| {
            ScoreOutcome::Failed(super::model_failure(
                error.to_string(),
                Some(planned.clone()),
            ))
        };
        if deadline.expired() {
            return fail(Error::Timeout);
        }
        let raw = match session.infer(&excerpt.ids) {
            Ok(raw) => raw,
            Err(error) => return fail(error),
        };
        if deadline.expired() {
            return fail(Error::Timeout);
        }
        let threshold_key = if self.manifest.id == "conpara" {
            "checkpoint_threshold_margin"
        } else {
            "pilot_development_1pct"
        };
        let threshold = self.manifest.threshold(threshold_key);
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
            runtime: "candle-debertav2".into(),
            device: DEVICE.into(),
            precision: PRECISION.into(),
            preprocessing_revision: self.manifest.preprocessing_revision.clone(),
            raw_output: raw,
            raw_units: if self.manifest.id == "conpara" {
                "logit margin (AI - human; higher = machine-like)".into()
            } else {
                "logit (higher = machine-like at the pinned pilot cutoff)".into()
            },
            threshold,
            threshold_source: threshold.map(|_| {
                if self.manifest.id == "conpara" {
                    "checkpoint threshold_margin".into()
                } else {
                    "pilot development 1% target".into()
                }
            }),
            prepared_bytes: prepared.len(),
            prepared_words: doc.words.len(),
            excerpt_bytes: excerpt.bytes,
            excerpt_tokens: excerpt.tokens,
            token_limit: session.max_tokens,
            truncated: excerpt.truncated,
            planned_coverage: excerpt.coverage,
            execution_coverage: excerpt.coverage,
            excerpt_coverage: excerpt.coverage,
            elapsed_ms: started.elapsed().as_secs_f64() * 1000.0,
            packing_policy: None,
            aggregation_policy: None,
            windows: vec![],
            full_coverage_output: None,
            token_coverage: None,
            coverage_gaps: vec![],
            detectorscope: None,
        };
        let mut score: Score = model_score(&self.manifest.id);
        score.model_evidence = Some(evidence);
        score.metrics.insert(
            "model_score".into(),
            crate::score::Metric {
                value: raw,
                unit: if self.manifest.id == "conpara" {
                    "logit_margin"
                } else {
                    "logit"
                }
                .into(),
                method: self.manifest.preprocessing_revision.clone(),
            },
        );
        if let Some(threshold) = threshold {
            score.metrics.insert(
                "model_threshold".into(),
                crate::score::Metric {
                    value: threshold,
                    unit: "logit".into(),
                    method: threshold_key.into(),
                },
            );
        }
        ScoreOutcome::Scored(score)
    }
}

impl EncoderBackend {
    fn manifest_minimum_words(&self) -> usize {
        self.manifest.minimum_words.unwrap_or(25)
    }
}

struct Excerpt {
    ids: Vec<u32>,
    tokens: usize,
    bytes: usize,
    truncated: bool,
    coverage: Option<f64>,
}

fn load_tokenizer(manifest: &Manifest, root: &Path) -> Result<Tokenizer, Error> {
    let pin = manifest
        .tokenizer
        .as_ref()
        .ok_or_else(|| Error::ModelLoadFailed("manifest has no tokenizer pin".into()))?;
    let path = root.join(&pin.file);
    let bytes = super::read_verified(&path, &pin.sha256)?;
    Tokenizer::from_bytes(bytes).map_err(|e| Error::ModelLoadFailed(format!("tokenizer: {e}")))
}

fn build_excerpt(tokenizer: &Tokenizer, max_tokens: usize, text: &str) -> Result<Excerpt, Error> {
    let full = tokenizer
        .encode(text, true)
        .map_err(|e| Error::InternalError(format!("tokenizer: {e}")))?;
    let ids = full.get_ids();
    let total = ids.len();
    if total <= max_tokens {
        return Ok(Excerpt {
            ids: ids.to_vec(),
            tokens: total,
            bytes: text.len(),
            truncated: false,
            coverage: Some(1.0),
        });
    }
    let keep_body = max_tokens.saturating_sub(2);
    let sep = tokenizer
        .token_to_id("[SEP]")
        .or_else(|| tokenizer.token_to_id("</s>"))
        .ok_or_else(|| Error::InternalError("tokenizer has no separator token".into()))?;
    let mut kept: Vec<u32> = ids[..=keep_body.min(ids.len() - 1)].to_vec();
    kept.push(sep);
    let end = full
        .get_offsets()
        .get(keep_body)
        .map(|(_, end)| *end)
        .unwrap_or(text.len())
        .min(text.len());
    let end = floor_char_boundary(text, end);
    let coverage = if text.is_empty() {
        None
    } else {
        Some(text[..end].chars().count() as f64 / text.chars().count() as f64)
    };
    Ok(Excerpt {
        ids: kept.clone(),
        tokens: kept.len(),
        bytes: end,
        truncated: true,
        coverage,
    })
}

impl Session {
    fn load(manifest: &'static Manifest, root: &Path) -> Result<Self, Error> {
        let config_path = if manifest.id == "conpara" {
            root.join("conpara/config.json")
        } else {
            root.join("desklib/config.json")
        };
        let config_raw = super::read_verified(&config_path, artifact_sha(manifest, &config_path)?)?;
        let config: Config = serde_json::from_slice(&config_raw)
            .map_err(|e| Error::ModelLoadFailed(format!("config: {e}")))?;
        let tokenizer = load_tokenizer(manifest, root)?;
        let model_path = root.join(if manifest.id == "conpara" {
            "conpara/model.safetensors"
        } else {
            "desklib/model.safetensors"
        });
        // Verify the exact bytes, then hand that owned buffer to Candle. This avoids
        // an unsafe memory map of a file that could be mutated after verification.
        let weights = super::read_verified(&model_path, artifact_sha(manifest, &model_path)?)?;
        let vb =
            candle_nn::VarBuilder::from_buffered_safetensors(weights, DType::F32, &Device::Cpu)
                .map_err(|e| Error::ModelLoadFailed(format!("weights: {e}")))?;
        let prefix = if manifest.id == "conpara" {
            "encoder"
        } else {
            "model"
        };
        let model = DebertaV2Model::load(vb.pp(prefix), &config)
            .map_err(|e| Error::ModelLoadFailed(format!("deberta: {e}")))?;
        let classifier = if manifest.id == "conpara" {
            let first = candle_nn::linear(1024, 512, vb.pp("classifier.0"))
                .map_err(|e| Error::ModelLoadFailed(format!("classifier.0: {e}")))?;
            let second = candle_nn::linear(512, 2, vb.pp("classifier.3"))
                .map_err(|e| Error::ModelLoadFailed(format!("classifier.3: {e}")))?;
            Classifier::ConPara { first, second }
        } else {
            Classifier::Desklib(
                candle_nn::linear(1024, 1, vb.pp("classifier"))
                    .map_err(|e| Error::ModelLoadFailed(format!("classifier: {e}")))?,
            )
        };
        Ok(Self {
            model,
            classifier,
            tokenizer,
            max_tokens: manifest.max_tokens,
        })
    }

    fn infer(&self, ids: &[u32]) -> Result<f64, Error> {
        let length = ids.len();
        let input_ids = Tensor::from_vec(ids.to_vec(), (1, length), &Device::Cpu)
            .map_err(|e| Error::InternalError(format!("input ids: {e}")))?;
        let mask = Tensor::from_vec(vec![1u32; length], (1, length), &Device::Cpu)
            .map_err(|e| Error::InternalError(format!("attention mask: {e}")))?;
        let hidden = self
            .model
            .forward(&input_ids, None, Some(mask.clone()))
            .map_err(|e| Error::InternalError(format!("encoder: {e}")))?;
        match &self.classifier {
            Classifier::Desklib(classifier) => {
                let mask = mask
                    .to_dtype(DType::F32)
                    .and_then(|m| m.unsqueeze(D::Minus1))
                    .map_err(|e| Error::InternalError(format!("pool mask: {e}")))?;
                let pooled = hidden
                    .broadcast_mul(&mask)
                    .and_then(|h| h.sum(1))
                    .and_then(|h| {
                        let count = mask.sum(1)?;
                        h.broadcast_div(&count)
                    })
                    .map_err(|e| Error::InternalError(format!("masked mean: {e}")))?;
                let logits = classifier
                    .forward(&pooled)
                    .map_err(|e| Error::InternalError(format!("classifier: {e}")))?;
                tensor_scalar(&logits)
            }
            Classifier::ConPara { first, second } => {
                let cls = hidden
                    .narrow(1, 0, 1)
                    .and_then(|h| h.squeeze(1))
                    .map_err(|e| Error::InternalError(format!("cls pool: {e}")))?;
                let logits = first
                    .forward(&cls)
                    .and_then(|h| h.gelu_erf())
                    .and_then(|h| second.forward(&h))
                    .map_err(|e| Error::InternalError(format!("classifier: {e}")))?;
                let logits = logits
                    .to_dtype(DType::F64)
                    .map_err(|e| Error::InternalError(format!("logits: {e}")))?;
                let human = logits
                    .narrow(1, 0, 1)
                    .and_then(|t| {
                        tensor_scalar(&t).map_err(|e| match e {
                            Error::InternalError(msg) => candle_core::Error::Msg(msg),
                            _ => candle_core::Error::Msg("output".into()),
                        })
                    })
                    .map_err(|e| Error::InternalError(format!("human logit: {e}")))?;
                let ai = logits
                    .narrow(1, 1, 1)
                    .and_then(|t| {
                        tensor_scalar(&t).map_err(|e| match e {
                            Error::InternalError(msg) => candle_core::Error::Msg(msg),
                            _ => candle_core::Error::Msg("output".into()),
                        })
                    })
                    .map_err(|e| Error::InternalError(format!("ai logit: {e}")))?;
                Ok(ai - human)
            }
        }
    }
}

fn tensor_scalar(t: &Tensor) -> Result<f64, Error> {
    let values = t
        .flatten_all()
        .and_then(|t| t.to_dtype(DType::F64))
        .and_then(|t| t.to_vec1::<f64>())
        .map_err(|e| Error::InternalError(format!("output: {e}")))?;
    values
        .first()
        .copied()
        .ok_or_else(|| Error::InternalError("empty model output".into()))
}

fn floor_char_boundary(text: &str, mut end: usize) -> usize {
    end = end.min(text.len());
    while end > 0 && !text.is_char_boundary(end) {
        end -= 1;
    }
    end
}

fn artifact_sha<'a>(manifest: &'a Manifest, path: &Path) -> Result<&'a str, Error> {
    manifest
        .artifacts
        .iter()
        .find(|artifact| path.ends_with(&artifact.path))
        .map(|artifact| artifact.sha256.as_str())
        .ok_or_else(|| Error::InternalError(format!("no manifest digest for {}", path.display())))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    fn fixture() -> Value {
        serde_json::from_str(include_str!(
            "../../tests/fixtures/models/encoder-reference.json"
        ))
        .unwrap()
    }

    #[test]
    fn excerpt_token_ids_and_masks_match_pinned_tokenizer_fixture() {
        let Ok(root) = std::env::var("NOBOTRS_MODELS_DIR") else {
            eprintln!("skipping tokenizer parity; set NOBOTRS_MODELS_DIR");
            return;
        };
        let root = PathBuf::from(root);
        let fixture = fixture();
        for backend in ["desklib", "conpara"] {
            let manifest = super::super::manifest(backend).unwrap();
            let tokenizer = load_tokenizer(manifest, &root).unwrap();
            for case in fixture["cases"].as_array().unwrap() {
                let text = if backend == "conpara" {
                    super::super::normalize_input(case["text"].as_str().unwrap())
                } else {
                    case["text"].as_str().unwrap().to_string()
                };
                let excerpt = build_excerpt(&tokenizer, manifest.max_tokens, &text).unwrap();
                let expected: Vec<u32> = case[backend]["ids"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|value| value.as_u64().unwrap() as u32)
                    .collect();
                assert_eq!(excerpt.ids, expected, "{backend} token ids");
                let mask: Vec<u32> = case[backend]["attention_mask"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|value| value.as_u64().unwrap() as u32)
                    .collect();
                assert_eq!(mask, vec![1; excerpt.ids.len()], "{backend} all-one mask");
                assert_eq!(excerpt.tokens, excerpt.ids.len());
                assert_eq!(
                    excerpt.truncated,
                    case[backend]["truncated"].as_bool().unwrap()
                );
            }
        }
    }
}
