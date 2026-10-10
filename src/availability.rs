// src/availability.rs

#[derive(Debug, Clone, PartialEq)]
pub enum Availability {
    Ready,
    NeedsDownload,
    Unavailable(String),
}
