use serde::Deserialize;
use std::collections::HashMap;
use unicode_general_category::{get_general_category, GeneralCategory};
use unicode_normalization::UnicodeNormalization;

#[derive(Deserialize)]
struct Tables {
    single: HashMap<char, String>,
    multi: Vec<(String, String)>,
}

const TABLES: &str = include_str!("../../models/conpara-unicode-v2.json");

fn tables() -> Tables {
    serde_json::from_str(TABLES).expect("embedded ConPara unicode tables are valid")
}

/// Port of the pinned ConPara `unicode_preprocessing_v2.unicode_normalize` order:
/// explicit single-character table, ordered multi-character replacement, NFKD +
/// mark stripping, NFC, format-character stripping, then repeated-space collapse.
pub fn conpara_unicode(text: &str) -> String {
    let tables = tables();
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match tables.single.get(&c) {
            Some(replacement) => out.push_str(replacement),
            None => out.push(c),
        }
    }
    for (source, replacement) in &tables.multi {
        if out.contains(source) {
            out = out.replace(source, replacement);
        }
    }
    let out: String = out
        .nfkd()
        .filter(|c| get_general_category(*c) != GeneralCategory::NonspacingMark)
        .collect();
    let out: String = out.nfc().collect();
    let out: String = out
        .chars()
        .filter(|c| get_general_category(*c) != GeneralCategory::Format)
        .collect();
    let mut out = out;
    while out.contains("  ") {
        out = out.replace("  ", " ");
    }
    out
}

/// Inference-time preprocessing used by ConPara: Unicode normalization then
/// whitespace collapse. Other backends continue to see canonical prepared prose.
pub fn conpara_input(text: &str) -> String {
    conpara_unicode(text)
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn typography_zero_width_and_mixed_scripts_follow_the_pinned_order() {
        assert_eq!(conpara_unicode("“A” — ﬁ"), "\"A\" -- fi");
        assert_eq!(conpara_unicode("a\u{200b}b"), "ab");
        assert_eq!(conpara_unicode("русский"), conpara_unicode("русский"));
        assert_eq!(conpara_input("  one\n\ttwo   three "), "one two three");
    }

    #[test]
    fn normalization_is_idempotent_on_synthetic_probes() {
        for text in ["é  ﬁ  —  “x”", "café\u{200b}", "ＡＢＣ – ½"] {
            let once = conpara_unicode(text);
            assert_eq!(conpara_unicode(&once), once);
        }
    }
}
