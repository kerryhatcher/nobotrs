// src/backends/mod.rs
//
// Deviation from the Task 8 brief: the brief's Step 3 snippet declares
// `pub mod burstiness; pub mod compression; pub mod lexical_diversity;
// pub mod punctuation; pub mod readability;` alongside `vocabulary`, but
// not all of those backends exist yet. `compression` and `readability` are
// not part of any task brief through Task 11, so those files do not exist —
// declaring them here would break compilation with "file not found for
// module" errors unrelated to the backends actually implemented so far.
// The remaining `pub mod` lines should be added by whichever task
// introduces each corresponding backend.
pub mod vocabulary;
pub mod punctuation;
pub mod burstiness;
pub mod lexical_diversity;
