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

/// Apply the pinned normalization while retaining original UTF-8 navigation ranges.
/// Tables are applied before compatibility decomposition, as in `conpara_unicode`.
pub fn conpara_input_with_map(text: &str) -> (String, Vec<std::ops::Range<usize>>) {
    use unicode_segmentation::UnicodeSegmentation;
    let tables = tables();
    let mut chars: Vec<(char, std::ops::Range<usize>)> = Vec::new();
    for (i, c) in text.char_indices() {
        let source = i..i + c.len_utf8();
        if let Some(replacement) = tables.single.get(&c) {
            chars.extend(replacement.chars().map(|c| (c, source.clone())));
        } else {
            chars.push((c, source));
        }
    }
    for (from, to) in &tables.multi {
        let needle: Vec<_> = from.chars().collect();
        if needle.is_empty() {
            continue;
        }
        let mut next = Vec::new();
        let mut i = 0;
        while i < chars.len() {
            if i + needle.len() <= chars.len()
                && chars[i..i + needle.len()]
                    .iter()
                    .map(|x| x.0)
                    .eq(needle.iter().copied())
            {
                let range = chars[i].1.start..chars[i + needle.len() - 1].1.end;
                next.extend(to.chars().map(|c| (c, range.clone())));
                i += needle.len();
            } else {
                next.push(chars[i].clone());
                i += 1;
            }
        }
        chars = next;
    }
    let intermediate: String = chars.iter().map(|x| x.0).collect();
    let mut byte_map = Vec::new();
    for (c, r) in chars {
        byte_map.extend(std::iter::repeat_n(r, c.len_utf8()));
    }
    let mut output = String::new();
    let mut mapping = Vec::new();
    let mut pending_space: Option<std::ops::Range<usize>> = None;
    for (start, cluster) in intermediate.grapheme_indices(true) {
        let end = start + cluster.len();
        let source = byte_map[start].start..byte_map[end - 1].end;
        let normalized: String = cluster
            .nfkd()
            .filter(|c| get_general_category(*c) != GeneralCategory::NonspacingMark)
            .collect::<String>()
            .nfc()
            .filter(|c| get_general_category(*c) != GeneralCategory::Format)
            .collect();
        for c in normalized.chars() {
            if c.is_whitespace() {
                if let Some(r) = &mut pending_space {
                    r.end = source.end;
                } else {
                    pending_space = Some(source.clone());
                }
                continue;
            }
            if let Some(r) = pending_space.take() {
                if !output.is_empty() {
                    output.push(' ');
                    mapping.push(r);
                }
            }
            output.push(c);
            mapping.extend(std::iter::repeat_n(source.clone(), c.len_utf8()));
        }
    }
    (output, mapping)
}
#[cfg(test)]
mod mapping_tests {
    use super::*;
    #[test]
    fn normalize_map_points_into_source_and_matches_pinned_order() {
        for text in [
            "  “café” — ﬁ \r\nＡＢＣ\u{200b} ",
            "e\u{301} 가 한국어",
            "one  two\nthree",
            "русский ½",
            "foo\u{200b}bar",
        ] {
            let (out, map) = conpara_input_with_map(text);
            assert_eq!(out, conpara_input(text));
            assert_eq!(out.len(), map.len());
            for r in map {
                assert!(!r.is_empty());
                assert!(text.get(r).is_some());
            }
        }
    }
}
