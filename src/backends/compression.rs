// src/backends/compression.rs
use std::collections::HashMap;

use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

const MIN_WORDS_FOR_STATS: usize = 150;

pub struct Compression;

/// LZMA compression ratio (compressed_len / raw_len) via `lzma_rs::lzma_compress`
/// with its default `Options` (spec §10 discusses this as a proxy for how
/// predictable/repetitive the prose is; lower ratio = more compressible).
///
/// Deviation from the Task 13 brief: the brief's snippet comment described
/// this as matching `check_ai_tells.py`'s `lzma.compress(raw, preset=6)`.
/// Task 13 Step 0 verified `lzma-rs` 0.3's real API against docs.rs
/// (https://docs.rs/lzma-rs/0.3.0/lzma_rs/fn.lzma_compress.html and
/// https://docs.rs/lzma-rs/0.3.0/lzma_rs/compress/struct.Options.html) and
/// found that `lzma_rs::compress::Options` exposes only one field,
/// `unpacked_size: UnpackedSize` (whether to write the decompressed size into
/// the header) — there is no preset/level knob at all in this crate version.
/// `lzma_compress` (default `Options`) is therefore the closest available
/// call; the "preset 6" framing does not apply to this crate and the ratio
/// this backend produces is not numerically comparable to the Python
/// reference implementation's preset-6 ratio. Since v1 treats `Compression`
/// as evidence-only (never above `VoteStrength::None`), this does not affect
/// any threshold decision.
#[cfg(test)]
pub(crate) fn compression_ratio(raw: &[u8]) -> f64 {
    compression_ratio_bounded(raw, Deadline::new(std::time::Duration::from_secs(10))).unwrap()
}
fn compression_ratio_bounded(raw: &[u8], deadline: Deadline) -> Result<f64, crate::error::Error> {
    if raw.is_empty() {
        return Ok(1.0);
    }
    Ok(compressed_bytes_bounded(raw, deadline)?.len() as f64 / raw.len() as f64)
}
/// The pinned LZMA-Alone stream for nonempty input. Kept separate from the ratio
/// so reference tests can pin the exact bytes and validate the container.
fn compressed_bytes_bounded(
    raw: &[u8],
    deadline: Deadline,
) -> Result<Vec<u8>, crate::error::Error> {
    use std::io::{BufRead, Read};
    struct BudgetReader<'a> {
        raw: &'a [u8],
        deadline: Deadline,
    }
    impl Read for BudgetReader<'_> {
        fn read(&mut self, out: &mut [u8]) -> std::io::Result<usize> {
            if self.deadline.expired() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::TimedOut,
                    "analysis deadline exceeded",
                ));
            }
            self.raw.read(out)
        }
    }
    impl BufRead for BudgetReader<'_> {
        fn fill_buf(&mut self) -> std::io::Result<&[u8]> {
            if self.deadline.expired() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::TimedOut,
                    "analysis deadline exceeded",
                ));
            }
            Ok(self.raw)
        }
        fn consume(&mut self, n: usize) {
            self.raw = &self.raw[n..];
        }
    }
    let mut compressed = vec![];
    if let Err(error) = lzma_rs::lzma_compress(&mut BudgetReader { raw, deadline }, &mut compressed)
    {
        return Err(if deadline.expired() {
            crate::error::Error::Timeout
        } else {
            crate::error::Error::InternalError(error.to_string())
        });
    }
    if deadline.expired() {
        return Err(crate::error::Error::Timeout);
    }
    Ok(compressed)
}

/// Shannon entropy (bits) over the document's word-frequency distribution —
/// a proxy for how predictable the token stream is, bundled into this
/// backend's evidence rather than a separate family (spec §2.2).
#[cfg(test)]
pub(crate) fn entropy_per_token(words: &[&str]) -> f64 {
    entropy_bounded(words, None).unwrap()
}
fn entropy_bounded(words: &[&str], deadline: Option<Deadline>) -> Option<f64> {
    if deadline.is_some_and(|d| d.expired()) {
        return None;
    }
    if words.is_empty() {
        return Some(0.0);
    }
    let mut freq: HashMap<&str, usize> = HashMap::new();
    for w in words {
        if deadline.is_some_and(|d| d.expired()) {
            return None;
        }
        *freq.entry(*w).or_insert(0) += 1;
    }
    let n = words.len() as f64;
    let mut entropy = 0.0;
    for &count in freq.values() {
        if deadline.is_some_and(|d| d.expired()) {
            return None;
        }
        let p = count as f64 / n;
        entropy += p * p.log2();
    }
    Some(-entropy)
}

impl DetectorBackend for Compression {
    fn name(&self) -> &str {
        "compression"
    }
    fn family(&self) -> SignalFamily {
        SignalFamily::Compression
    }
    fn availability(&self) -> Availability {
        Availability::Ready
    }

    fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome {
        if deadline.expired() {
            return ScoreOutcome::Failed(crate::error::Error::Timeout);
        }
        let word_count = doc.words.len();
        if word_count < MIN_WORDS_FOR_STATS {
            return ScoreOutcome::Abstained {
                reason: format!(
                    "text has {word_count} words, below the {MIN_WORDS_FOR_STATS}-word floor"
                ),
            };
        }

        let prose = &doc.prose;
        let ratio = match compression_ratio_bounded(prose.as_bytes(), deadline) {
            Ok(ratio) => ratio,
            Err(error) => return ScoreOutcome::Failed(error),
        };
        let mut words = Vec::new();
        for word in prose.split_whitespace() {
            if deadline.expired() {
                return ScoreOutcome::Failed(crate::error::Error::Timeout);
            }
            words.push(word);
        }
        let Some(entropy) = entropy_bounded(&words, Some(deadline)) else {
            return ScoreOutcome::Failed(crate::error::Error::Timeout);
        };

        // Evidence-only in v1 (spec §2.2, §7 item 5): always VoteStrength::None.

        if deadline.expired() {
            return ScoreOutcome::Failed(crate::error::Error::Timeout);
        }
        ScoreOutcome::Scored(
            Score::new(
                "compression".to_string(),
                SignalFamily::Compression,
                ConfidenceTier::Low,
                VoteStrength::None,
                vec![],
            )
            .metric(
                "lzma_ratio",
                ratio,
                "compressed-bytes/prose-bytes",
                "lzma-rs-0.3-default",
            )
            .metric(
                "token_entropy",
                entropy,
                "bits/token",
                "shannon-whitespace-case-sensitive-v1",
            ),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn entropy_of_all_identical_tokens_is_zero() {
        let tokens = vec!["same"; 50];
        assert_eq!(entropy_per_token(&tokens), 0.0);
    }

    #[test]
    fn entropy_of_all_unique_tokens_is_log2_of_count() {
        let owned: Vec<String> = (0..16).map(|i| format!("t{i}")).collect();
        let tokens: Vec<&str> = owned.iter().map(|s| s.as_str()).collect();
        let entropy = entropy_per_token(&tokens);
        assert!(
            (entropy - 4.0).abs() < 1e-9,
            "16 equally-likely unique tokens should have entropy log2(16)=4.0, got {entropy}"
        );
    }

    #[test]
    fn compression_ratio_of_highly_repetitive_text_is_low() {
        let repetitive = "the same words repeat over and over again ".repeat(50);
        let ratio = compression_ratio(repetitive.as_bytes());
        assert!(
            ratio < 0.5,
            "highly repetitive text should compress well (low ratio), got {ratio}"
        );
    }

    #[test]
    fn under_150_words_abstains() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        let backend = Compression;
        let doc = Document::from_stdin_text("short text".to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        assert!(matches!(
            backend.score(&doc, deadline),
            ScoreOutcome::Abstained { .. }
        ));
    }

    #[test]
    fn evidence_only_never_votes_above_none() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        use crate::score::VoteStrength;
        let backend = Compression;
        let text = "the same words repeat over and over again ".repeat(50);
        let doc = Document::from_stdin_text(text, false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        if let ScoreOutcome::Scored(score) = backend.score(&doc, deadline) {
            assert_eq!(score.vote, VoteStrength::None);
        }
    }

    fn unhex(hex: &str) -> Vec<u8> {
        assert!(hex.len() % 2 == 0, "odd-length hex fixture");
        hex.as_bytes()
            .chunks_exact(2)
            .map(|pair| {
                let text = std::str::from_utf8(pair).unwrap();
                u8::from_str_radix(text, 16).unwrap()
            })
            .collect()
    }

    #[test]
    fn pinned_compression_reference() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../tests/fixtures/compression-reference.json"
        ))
        .unwrap();
        let reference = &fixture["reference"];
        assert_eq!(reference["crate"], "lzma-rs");
        assert_eq!(reference["version"], "0.3.0");
        assert_eq!(
            reference["crates_io_checksum"],
            "297e814c836ae64db86b36cf2a557ba54368d03f6afcd7d947c266692f71115e"
        );
        let tolerance = reference["comparison_tolerance"].as_f64().unwrap();
        let cases = fixture["cases"].as_array().unwrap();
        assert_eq!(cases.len(), 7);
        let deadline = Deadline::new(std::time::Duration::from_secs(5));
        for case in cases {
            let id = case["id"].as_str().unwrap();
            let text = case["text"].as_str().unwrap();
            let doc = Document::from_stdin_text(text.to_string(), false);
            assert_eq!(
                doc.prose.len(),
                case["expected_prose_bytes"].as_u64().unwrap() as usize,
                "{id}: prepared prose bytes"
            );
            assert_eq!(
                doc.words.len(),
                case["expected_document_words"].as_u64().unwrap() as usize,
                "{id}: document words"
            );
            let tokens: Vec<&str> = doc.prose.split_whitespace().collect();
            assert_eq!(
                tokens.len(),
                case["expected_tokens"].as_u64().unwrap() as usize,
                "{id}: whitespace tokens"
            );
            let expected_entropy = case["expected_entropy"].as_f64().unwrap();
            let entropy = entropy_bounded(&tokens, Some(deadline)).unwrap();
            assert!(
                (entropy - expected_entropy).abs() < tolerance,
                "{id}: entropy {entropy} vs {expected_entropy}"
            );
            let expected_ratio = case["expected_lzma_ratio"].as_f64().unwrap();
            let ratio = compression_ratio_bounded(doc.prose.as_bytes(), deadline).unwrap();
            assert!(
                (ratio - expected_ratio).abs() < tolerance,
                "{id}: ratio {ratio} vs {expected_ratio}"
            );
            match case["lzma_alone_hex"].as_str() {
                None => {
                    assert!(
                        doc.prose.is_empty(),
                        "{id}: only empty prose lacks a stream"
                    );
                    assert_eq!(case["expected_compressed_bytes"], 0, "{id}");
                    assert!(case["expected_lzma_sha256"].is_null(), "{id}");
                }
                Some(hex) => {
                    let expected_stream = unhex(hex);
                    assert_eq!(
                        expected_stream.len(),
                        case["expected_compressed_bytes"].as_u64().unwrap() as usize,
                        "{id}: pinned stream length"
                    );
                    let stream = compressed_bytes_bounded(doc.prose.as_bytes(), deadline).unwrap();
                    assert_eq!(stream, expected_stream, "{id}: pinned LZMA-Alone bytes");
                    let mut decoded = vec![];
                    lzma_rs::lzma_decompress(
                        &mut std::io::Cursor::new(&expected_stream),
                        &mut decoded,
                    )
                    .unwrap();
                    assert_eq!(decoded, doc.prose.as_bytes(), "{id}: decompressed prose");
                }
            }
            let expected_words = case["expected_document_words"].as_u64().unwrap() as usize;
            let actual = Compression.score(&doc, deadline);
            if expected_words < MIN_WORDS_FOR_STATS {
                assert!(
                    matches!(actual, ScoreOutcome::Abstained { .. }),
                    "{id}: below-floor case must abstain, got {actual:?}"
                );
                assert_eq!(case["expected_backend_outcome"], "abstained", "{id}");
            } else {
                let ScoreOutcome::Scored(score) = actual else {
                    panic!("{id}: backend did not score")
                };
                assert!(
                    (score.metrics["lzma_ratio"].value - expected_ratio).abs() < tolerance,
                    "{id}: backend ratio"
                );
                assert!(
                    (score.metrics["token_entropy"].value - expected_entropy).abs() < tolerance,
                    "{id}: backend entropy"
                );
                assert_eq!(
                    score.metrics["lzma_ratio"].method, "lzma-rs-0.3-default",
                    "{id}"
                );
                assert_eq!(
                    score.metrics["token_entropy"].method, "shannon-whitespace-case-sensitive-v1",
                    "{id}"
                );
                assert_eq!(score.vote, VoteStrength::None, "{id}");
                assert_eq!(case["expected_backend_outcome"], "scored", "{id}");
            }
        }
    }
}
