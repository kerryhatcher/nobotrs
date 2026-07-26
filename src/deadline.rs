// src/deadline.rs
use std::time::{Duration, Instant};

/// A cooperative budget, NOT a preemption mechanism (spec §2.1). A callee that
/// never polls `expired()` will not be interrupted by this type — it has no
/// effect on code already blocked in FFI, a blocking network call, or a tight
/// loop that never checks it.
#[allow(dead_code)] // Temporary: consumed starting in Task 3
#[derive(Debug, Clone, Copy)]
pub struct Deadline {
    deadline: Instant,
}

impl Deadline {
    #[allow(dead_code)] // Temporary: consumed starting in Task 3
    pub fn new(budget: Duration) -> Self {
        Deadline { deadline: Instant::now() + budget }
    }

    #[allow(dead_code)] // Temporary: consumed starting in Task 3
    pub fn expired(&self) -> bool {
        Instant::now() >= self.deadline
    }

    #[allow(dead_code)] // Temporary: consumed starting in Task 3
    pub fn remaining(&self) -> Duration {
        self.deadline.saturating_duration_since(Instant::now())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn not_expired_immediately_after_creation() {
        let d = Deadline::new(Duration::from_secs(5));
        assert!(!d.expired());
    }

    #[test]
    fn expired_after_budget_elapses() {
        let d = Deadline::new(Duration::from_millis(1));
        std::thread::sleep(Duration::from_millis(20));
        assert!(d.expired());
    }
}
