// src/backends/mod.rs
//
// Deviation from the Task 8 brief: the brief's Step 3 snippet declares
// `pub mod burstiness; pub mod compression; pub mod lexical_diversity;
// pub mod punctuation; pub mod readability;` alongside `vocabulary`, but
// not all of those backends exist yet. `compression` is not part of any
// task brief through Task 12, so that file does not exist — declaring it
// here would break compilation with a "file not found for module" error
// unrelated to the backends actually implemented so far. The remaining
// `pub mod` line should be added by whichever task introduces that backend.
pub mod vocabulary;
pub mod punctuation;
pub mod burstiness;
pub mod lexical_diversity;
pub mod readability;
