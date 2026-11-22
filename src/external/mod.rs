//! Opt-in external evidence (feature `api-clients` for the network clients).
//!
//! Everything here is informational. Results are attached to a report as side channels and
//! never enter the heuristic families, quorum, or exit verdict.

use serde::Serialize;

pub mod gptzero;
pub mod openrouter;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExternalStatus {
    Ok,
    Skipped,
    Failed,
}
