//! Local evaluation worker. One JSON path per line, one editorial report per response.
use nobotrs::{config::Settings, pipeline::Engine, score::Severity};
use std::io::{self, BufRead, Write};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let settings = Settings {
        language: Some("en".into()),
        display_limit: 100_000,
        minimum_severity: Severity::Low,
        ..Settings::default()
    };
    let engine = Engine::new()?;
    let mut output = io::BufWriter::new(io::stdout().lock());
    for request in io::stdin().lock().lines() {
        let path: String = serde_json::from_str(&request?)?;
        let result = std::fs::metadata(&path)
            .and_then(|meta| {
                if meta.len() > settings.max_bytes as u64 {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "input exceeds maximum bytes",
                    ));
                }
                std::fs::read_to_string(&path)
            })
            .map_err(|error| error.to_string())
            .and_then(|text| engine.review(text, false, &path, &settings));
        match result {
            Ok(report) => serde_json::to_writer(&mut output, &report)?,
            Err(error) => serde_json::to_writer(
                &mut output,
                &serde_json::json!({"error":error, "complete":false}),
            )?,
        }
        output.write_all(b"\n")?;
        output.flush()?;
    }
    Ok(())
}
