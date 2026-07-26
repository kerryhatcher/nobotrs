// src/availability.rs

#[allow(dead_code)] // Temporary: consumed starting in Task 3
#[derive(Debug, Clone, PartialEq)]
pub enum Availability {
    Ready,
    NeedsDownload,
    Unavailable(String),
}
