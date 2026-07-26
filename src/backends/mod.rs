// src/backends/mod.rs
//
// Deviation from the Task 8 brief: the brief's Step 3 snippet declares
// `pub mod burstiness; pub mod compression; pub mod lexical_diversity;
// pub mod punctuation; pub mod readability;` alongside `vocabulary`, but
// those backends are not part of Task 8 — no task brief past Task 8 exists
// yet in this plan, so those files do not exist. Declaring them here would
// break compilation with "file not found for module" errors unrelated to
// Vocabulary. Only `vocabulary` is wired; the remaining `pub mod` lines
// should be added by whichever task introduces each corresponding backend.
pub mod vocabulary;
pub mod punctuation;
