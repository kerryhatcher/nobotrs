# GPTZero live spike notes (Task 0)

Captured 2026-11-21 with `POST https://api.gptzero.me/v2/predict/text`, header `x-api-key`, body `{"document": "<text>"}`. No `version` field was sent and the call succeeded. Raw responses were kept local and are not committed (GPTZero Terms of Use, sections 2 and 8). `tests/fixtures/gptzero/` holds hand-written synthetic fixtures that follow the observed schema. The key was never written to disk or echo'd.

## Request

- `document` (string): required in practice. Documented limit: 150,000 characters on API plans (400 when exceeded).
- `version`: not required. Not sent by the client.

## Response (observed)

Top level: `documents` (array), `version`, `neatVersion`, `scanId`, `editorDocumentId`.

Each `documents[0]` has, among 23 keys:

- `document_classification`: `AI_ONLY` observed. Documented values: `HUMAN_ONLY`, `MIXED`, `AI_ONLY`.
- `predicted_class`: `ai` observed. Documented values: `human`, `ai`, `mixed`.
- `confidence_category`: `high` observed.
- `class_probabilities`: `{human, ai, mixed}`. Integer values (0 or 1) at document level in both samples.
- `completely_generated_prob`, `average_generated_prob`: numeric, integral in both samples.
- `result_message`: human-readable sentence.
- `paragraphs[]`: `start_sentence_index`, `num_sentences`, `completely_generated_prob`.
- `sentences[]`: `sentence`, `generated_prob` (float), `perplexity`, `class_probabilities` with keys `human`, `ai`, `paraphrased` (float), `highlight_sentence_for_ai`, `should_mask`, `interpretability_*`.
- `subclass.ai.predicted_class`: `pure_ai` observed.
- `language`, `writing_stats`, `confidence_thresholds_raw`, `document_id`, `inputText`.

## Differences from the public reference

- The reference documents only `documents`, `version`, `predicted_class`, `class_probabilities`, `confidence_category`, `result_message`. The live response has many more fields.
- Sentence-level `class_probabilities` uses `paraphrased`, while document-level uses `mixed`. Inconsistent naming; the client reads document-level only.
- Document-level probabilities arrived as integers in both samples. Two samples cannot show whether they are always rounded.

## Client decision

The client deserializes only `documents[].{predicted_class, confidence_category, class_probabilities, document_classification, result_message}` and `version`, and ignores everything else. Unknown fields are not rejected, so a server-side addition does not break the tool.

## Observed result on the two samples

| Sample | GPTZero | nobotrs (heuristic) |
|---|---|---|
| Human-style personal essay (881 characters) | `AI_ONLY`, high confidence (false positive by reading) | `Clean` |
| Generic AI-style paragraph (~85 words) | `AI_ONLY`, high confidence | `Clean` |

Two samples are not evidence about either tool's accuracy. They show that the two tools disagree in at least one case, which is why the comparison is informational.
