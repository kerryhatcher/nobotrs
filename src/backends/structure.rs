//! Experimental editorial observations. Never eligible for detection votes.
use crate::{
    availability::Availability,
    backend::{DetectorBackend, ScoreOutcome, SignalFamily},
    deadline::Deadline,
    document::{ContentType, Document},
    error::Error,
    score::{ConfidenceTier, Score, Severity, VoteStrength},
    sentences::{paragraphs, sentence_units_with_deadline, SentenceUnit, UnitKind},
};
use regex::Regex;
use std::{ops::Range, sync::OnceLock};
use unicode_segmentation::UnicodeSegmentation;

pub const RULE_IDS: &[&str] = &[
    "structure.negative-parallelism",
    "structure.rule-of-three",
    "structure.coordinated-series",
    "structure.significance-inflation",
    "structure.copula-avoidance",
    "structure.cheerful-opener",
    "structure.short-fragment",
    "structure.summary-close",
    "structure.challenges-future-formula",
    "structure.repeated-opening",
    "structure.fragment-pattern",
    "structure.uniform-paragraphs",
    "structure.bold-inline-headers",
    "structure.title-case-headings",
    "structure.list-heavy",
];
// A closed editorial lexicon; an adjective match is a prompt, not a grammatical parse.
const ADJECTIVES: &[&str] = &[
    "robust",
    "seamless",
    "innovative",
    "efficient",
    "effective",
    "powerful",
    "flexible",
    "scalable",
    "reliable",
    "secure",
    "simple",
    "clear",
    "fast",
    "easy",
    "strong",
    "dynamic",
    "vibrant",
    "inclusive",
    "sustainable",
    "transformative",
    "comprehensive",
    "holistic",
    "strategic",
    "agile",
    "resilient",
    "transparent",
    "accountable",
    "excellent",
    "accessible",
    "adaptable",
    "affordable",
    "bold",
    "collaborative",
    "creative",
    "dependable",
    "diverse",
    "engaging",
    "intuitive",
    "modern",
    "versatile",
];
fn patterns() -> &'static Vec<(&'static str, Regex)> {
    static PATTERNS: OnceLock<Vec<(&str, Regex)>> = OnceLock::new();
    PATTERNS.get_or_init(|| [
        (RULE_IDS[0], r"(?i)\b(?:not (?:just|only|merely) [^,.;]{1,60}[,;—-]+ (?:but|it['’]?s|they['’]?re|this is)\b|isn['’]?t [^,.;]{1,40}[,;—-]+ it['’]?s\b|not because [^,.;]{1,60}, but because\b)"),
        (RULE_IDS[3], r"(?i)\b(?:serves as a (?:testament|reminder|beacon)|marks a (?:pivotal|significant|major) (?:moment|step|milestone)|(?:underscores|highlights) the (?:importance|need)|reflects a broader|stands as a|a (?:crucial|vital|pivotal) (?:step|role|moment)|in the (?:ever-)?(?:evolving|changing) (?:world|landscape))\b"),
        (RULE_IDS[4], r"(?i)\b(?:(?:serves|stands|functions|acts) as|boasts)\s+(?:\w+\s+){0,3}\w+[.!?,;]?$"),
        (RULE_IDS[5], r"(?i)^(?:great question|certainly|absolutely|of course|i['’]?d be happy to|sure thing)[!,.]"),
        (RULE_IDS[8], r"(?i)^(?:challenges and (?:future|opportunities)|despite (?:these|its) challenges|looking ahead)\b"),
    ].into_iter().map(|(id,p)| (id,Regex::new(p).expect("structural regex"))).collect())
}
pub struct Structure;
impl DetectorBackend for Structure {
    fn name(&self) -> &str {
        "structure"
    }
    fn family(&self) -> SignalFamily {
        SignalFamily::Structure
    }
    fn availability(&self) -> Availability {
        Availability::Ready
    }
    fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome {
        self.score_limited(doc, deadline, 10_000)
    }
}
struct Collector<'a> {
    doc: &'a Document,
    deadline: Deadline,
    cap: usize,
    score: Score,
}
impl Collector<'_> {
    fn add(&mut self, range: Range<usize>, id: &str, message: &str) -> Result<(), Error> {
        if self.deadline.expired() {
            return Err(Error::Timeout);
        }
        if self.score.candidates.len() >= self.cap {
            return Err(Error::ResourceLimit("structure candidate budget".into()));
        }
        if self
            .score
            .candidates
            .iter()
            .any(|e| e.rule_id == id && e.prose_offset == range)
        {
            return Ok(());
        }
        let mut e = self.doc.finding(range, id, Some(message.into()));
        e.severity = Severity::Low;
        self.score.candidates.push(e);
        Ok(())
    }
}
impl Structure {
    pub fn score_limited(&self, doc: &Document, deadline: Deadline, cap: usize) -> ScoreOutcome {
        if deadline.expired() {
            return ScoreOutcome::Failed(Error::Timeout);
        }
        if !doc.english_supported() {
            return ScoreOutcome::Abstained {
                reason: "structural rules require --language en".into(),
                model: None,
            };
        }
        if doc.words.is_empty() {
            return ScoreOutcome::Abstained {
                reason: "no analyzable prose".into(),
                model: None,
            };
        }
        let mut c = Collector {
            doc,
            deadline,
            cap,
            score: Score::new(
                "structure".into(),
                SignalFamily::Structure,
                ConfidenceTier::Low,
                VoteStrength::None,
                vec![],
            ),
        };
        let result = if let Some(units) = &doc.editorial_units {
            analyze(&mut c, units)
        } else {
            sentence_units_with_deadline(doc, deadline).and_then(|units| analyze(&mut c, &units))
        };
        c.score.evidence = c.score.candidates.clone();
        let count = c.score.candidates.len();
        c.score = c.score.metric(
            "structure_findings_per_1k_words",
            count as f64 * 1000.0 / doc.words.len().max(1) as f64,
            "findings/1k words",
            "structure-v1",
        );
        match result {
            Ok(()) => ScoreOutcome::Scored(c.score),
            Err(reason) => ScoreOutcome::Incomplete {
                score: c.score,
                reason,
                coverage: 0.0,
            },
        }
    }
}
fn abstract_or_adjective(word: &str) -> bool {
    ADJECTIVES.contains(&word)
        || ["ity", "ness", "tion", "ment", "ance", "ence"]
            .iter()
            .any(|s| word.ends_with(s))
}
fn triad(text: &str) -> bool {
    let Some((left, right)) = text.rsplit_once(" and ") else {
        return false;
    };
    let left = left.trim_end_matches(',');
    let Some((a, b)) = left.rsplit_once(',') else {
        return false;
    };
    let aw: Vec<_> = a.unicode_words().collect();
    let a = aw.last().copied().unwrap_or("");
    let b: Vec<_> = b.unicode_words().collect();
    let cw: Vec<_> = right.unicode_words().take(3).collect();
    let Some(c) = cw.first() else {
        return false;
    };
    if b.is_empty() || b.len() > 3 {
        return false;
    }
    let words = [a, b[0], c];
    if words
        .iter()
        .any(|w| w.chars().any(char::is_numeric) || w.starts_with(char::is_uppercase))
        || text.contains('$')
    {
        return false;
    }
    words
        .iter()
        .filter(|w| abstract_or_adjective(&w.to_lowercase()))
        .count()
        >= 2
}
fn gerund_range(text: &str) -> Option<Range<usize>> {
    let parts: Vec<_> = text
        .split([','])
        .flat_map(|p| p.split(" and "))
        .map(str::trim)
        .filter(|p| !p.is_empty())
        .collect();
    let mut heads = Vec::new();
    for part in parts {
        let mut words = part.unicode_words();
        let mut head = words.next().unwrap_or("");
        if ["after", "before", "by", "while", "when"].contains(&head.to_lowercase().as_str()) {
            head = words.next().unwrap_or("");
        }
        let lower = head.to_lowercase();
        if lower.len() >= 5 && lower.ends_with("ing") {
            heads.push(head);
        } else if !heads.is_empty() {
            break;
        }
    }
    if heads.len() < 3 {
        return None;
    }
    let start = heads[0].as_ptr() as usize - text.as_ptr() as usize;
    Some(start..text.len())
}
fn analyze(c: &mut Collector<'_>, u: &[SentenceUnit]) -> Result<(), Error> {
    let mut fragments = Vec::new();
    for (i, x) in u.iter().enumerate() {
        if c.deadline.expired() {
            return Err(Error::Timeout);
        }
        let text = &c.doc.prose[x.prose.clone()];
        if x.kind == UnitKind::Sentence {
            for (id, re) in patterns() {
                if *id == RULE_IDS[8] {
                    continue;
                }
                if *id == RULE_IDS[5] && i > 0 && u[i - 1].paragraph == x.paragraph {
                    continue;
                }
                for m in re.find_iter(text) {
                    c.add(x.prose.start+m.start()..x.prose.start+m.end(),id,"Check whether this pattern makes the point harder to follow; retain justified wording.")?;
                }
            }
            if triad(text) {
                c.add(x.prose.clone(),RULE_IDS[1],"Consider naming the concrete properties rather than a string of general qualities.")?;
            }
            if let Some(r) = gerund_range(text) {
                c.add(
                    x.prose.start + r.start..x.prose.start + r.end,
                    RULE_IDS[2],
                    "Check that each coordinated action is distinct and its relationship is clear.",
                )?;
            }
            if x.words <= 3 {
                fragments.push(i);
                c.add(x.prose.clone(),RULE_IDS[6],"Short-unit annotation; a complete short sentence or a deliberate fragment can be appropriate.")?;
            }
        }
        if (x.kind == UnitKind::Heading || i == 0 || u[i - 1].paragraph != x.paragraph)
            && patterns().last().unwrap().1.is_match(text)
        {
            c.add(
                x.prose.clone(),
                RULE_IDS[8],
                "Use a heading or transition specific to the actual next point.",
            )?;
        }
    }
    let paras = paragraphs(u);
    if let Some(last) = paras.last() {
        for (n, x) in u[last.clone()].iter().enumerate() {
            let t = x.text.to_lowercase();
            let summary = n == 0
                && [
                    "in conclusion",
                    "in summary",
                    "ultimately",
                    "overall",
                    "to sum up",
                    "all in all",
                ]
                .iter()
                .any(|s| t.starts_with(s));
            if summary
                || [
                    "as we move forward",
                    "as we look forward",
                    "as we move ahead",
                    "as we look ahead",
                    "the future of",
                ]
                .iter()
                .any(|s| t.contains(s))
            {
                c.add(
                    x.prose.clone(),
                    RULE_IDS[7],
                    "End on the useful conclusion; keep a summary when readers need one.",
                )?;
            }
        }
    }
    let mut seen = std::collections::HashSet::new();
    for window in u.windows(5.min(u.len()).max(1)) {
        if c.deadline.expired() {
            return Err(Error::Timeout);
        }
        for x in window.iter().filter(|x| x.kind == UnitKind::Sentence) {
            let opening = x
                .text
                .unicode_words()
                .take(2)
                .collect::<Vec<_>>()
                .join(" ")
                .to_lowercase();
            if opening.split_whitespace().count() < 2 {
                continue;
            }
            let same: Vec<_> = window
                .iter()
                .filter(|y| {
                    y.kind == UnitKind::Sentence
                        && y.text
                            .unicode_words()
                            .take(2)
                            .collect::<Vec<_>>()
                            .join(" ")
                            .to_lowercase()
                            == opening
                })
                .collect();
            if same.len() >= 3 && seen.insert(opening) {
                c.add(same[0].prose.clone(),RULE_IDS[9],"Repeated opening annotation: retain deliberate repetition, dialogue and parallel instructions.")?;
            }
        }
    }
    if fragments.len() >= 2
        && fragments.len() as f64 * 500.0 / c.doc.words.len().max(1) as f64 >= 3.0
    {
        c.add(u[fragments[0]].prose.clone(),RULE_IDS[10],&format!("{} short units; distinguish complete sentences, dialogue and deliberate emphasis before editing.",fragments.len()))?;
    }
    let lengths: Vec<_> = paras
        .iter()
        .filter(|p| {
            u[(*p).clone()]
                .iter()
                .filter(|x| x.kind == UnitKind::Sentence)
                .count()
                >= 2
        })
        .map(|p| u[p.clone()].iter().map(|x| x.words).sum::<usize>())
        .collect();
    if lengths.len() >= 5 {
        let mean = lengths.iter().sum::<usize>() as f64 / lengths.len() as f64;
        let cv = (lengths
            .iter()
            .map(|&n| (n as f64 - mean).powi(2))
            .sum::<f64>()
            / lengths.len() as f64)
            .sqrt()
            / mean;
        if cv < 0.25 {
            c.add(
                u[0].prose.clone(),
                RULE_IDS[11],
                "Similar paragraph lengths are an observation; vary only if the argument benefits.",
            )?;
        }
    }
    let headings: Vec<_> = u
        .iter()
        .filter(|x| {
            x.kind == UnitKind::Heading
                && x.words >= 3
                && x.text
                    .unicode_words()
                    .filter(|w| w.chars().count() >= 4)
                    .all(|w| w.starts_with(char::is_uppercase))
        })
        .collect();
    if headings.len() >= 3 {
        c.add(
            headings[0].prose.clone(),
            RULE_IDS[13],
            "Check heading case against the venue's style; title case may be required.",
        )?;
    }
    if c.doc.content_type == ContentType::Markdown {
        let bold: Vec<_> = paras
            .iter()
            .filter_map(|p| {
                let x = &u[p.start];
                c.doc
                    .strong_spans
                    .iter()
                    .find(|r| {
                        r.start == x.prose.start
                            && c.doc.prose[(*r).clone()].trim_end().ends_with(':')
                    })
                    .map(|_| x)
            })
            .collect();
        if bold.len() >= 3 {
            c.add(bold[0].prose.clone(),RULE_IDS[12],"Use actual headings when they aid navigation; keep compact labels in forms and reference lists.")?;
        }
        let list: Vec<_> = u.iter().filter(|x| x.kind == UnitKind::ListItem).collect();
        let words: usize = list.iter().map(|x| x.words).sum();
        if !list.is_empty()
            && words * 2 > c.doc.words.len()
            && list
                .iter()
                .filter(|x| x.text.ends_with(['.', '!', '?']))
                .count() as f64
                / list.len() as f64
                >= 0.6
        {
            c.add(list[0].prose.clone(),RULE_IDS[14],"Check whether connected prose would clarify relationships; retain procedures and factual lists.")?;
        }
    }
    if c.deadline.expired() {
        return Err(Error::Timeout);
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    fn score(t: &str, md: bool) -> Score {
        let mut d = Document::from_stdin_text(t.into(), md);
        d.assert_language(Some("en"));
        match Structure.score(&d, Deadline::new(std::time::Duration::from_secs(5))) {
            ScoreOutcome::Scored(s) => s,
            ScoreOutcome::Abstained { .. } => Score::new(
                "structure".into(),
                SignalFamily::Structure,
                ConfidenceTier::Low,
                VoteStrength::None,
                vec![],
            ),
            o => panic!("{o:?}"),
        }
    }
    fn count(t: &str, id: &str) -> usize {
        score(t, false)
            .evidence
            .iter()
            .filter(|e| e.rule_id == id)
            .count()
    }
    #[test]
    fn sentence_rules_and_controls() {
        for t in [
            "It isn't a budget, it's a warning.",
            "Not because they care, but because they must.",
            "This is not merely a tool; it’s a shift.",
        ] {
            assert_eq!(count(t, RULE_IDS[0]), 1, "{t}");
        }
        assert_eq!(
            count(
                "We value transparency, accountability, and excellence.",
                RULE_IDS[1]
            ),
            1
        );
        for t in [
            "The 2023, 2024 and 2025 budgets differ.",
            "Macon, Warner Robins and Perry voted.",
        ] {
            assert_eq!(count(t, RULE_IDS[1]), 0);
        }
        assert_eq!(count("After consolidating schools, freezing pay, packing classrooms, and contracting out staff.",RULE_IDS[2]),1);
        assert_eq!(
            count(
                "The building, the funding, and the staffing all lag behind.",
                RULE_IDS[2]
            ),
            0
        );
        assert_eq!(count("The library serves as a hub.", RULE_IDS[4]), 1);
        assert_eq!(count("Certainly! Here is the plan.", RULE_IDS[5]), 1);
        assert_eq!(count("The plan certainly helps.", RULE_IDS[5]), 0);
        assert_eq!(count("Still short.", RULE_IDS[6]), 1);
    }
    #[test]
    fn document_and_formatting_controls() {
        assert_eq!(
            count(
                "First we met.\n\nIn conclusion, budgets matter.",
                RULE_IDS[7]
            ),
            1
        );
        assert_eq!(count("Looking ahead\nThe work starts.", RULE_IDS[8]), 1);
        assert_eq!(
            count("We can vote. We can wait. We can listen.", RULE_IDS[9]),
            1
        );
        assert_eq!(count("Yes. No.", RULE_IDS[10]), 1);
        assert_eq!(
            count(
                "A full sentence explains the budget without introductory filler.",
                RULE_IDS[10]
            ),
            0
        );
        let uniform = ["We can read this. We can discuss it."; 5].join("\n\n");
        assert_eq!(count(&uniform, RULE_IDS[11]), 1);
        let md = "**One:** text.\n\n**Two:** text.\n\n**Three:** text.";
        assert_eq!(
            score(md, true)
                .evidence
                .iter()
                .filter(|e| e.rule_id == RULE_IDS[12])
                .count(),
            1
        );
        assert_eq!(
            score(
                "# First Heading Here\n\n# Second Heading Here\n\n# Third Heading Here",
                true
            )
            .evidence
            .iter()
            .filter(|e| e.rule_id == RULE_IDS[13])
            .count(),
            1
        );
        assert_eq!(
            score(
                "- First item is here.\n- Second item is here.\n- Third item is here.",
                true
            )
            .evidence
            .iter()
            .filter(|e| e.rule_id == RULE_IDS[14])
            .count(),
            1
        );
        assert!(score("```\nIn conclusion.\n**Bold:**\n```", true)
            .evidence
            .is_empty());
    }
    #[test]
    fn applicability_and_limits() {
        let d = Document::from_stdin_text("Certainly! Still short.".into(), false);
        assert!(matches!(
            Structure.score(&d, Deadline::new(std::time::Duration::from_secs(1))),
            ScoreOutcome::Abstained { .. }
        ));
        let mut d = d;
        d.assert_language(Some("en"));
        assert!(matches!(
            Structure.score_limited(&d, Deadline::new(std::time::Duration::from_secs(1)), 1),
            ScoreOutcome::Incomplete { .. }
        ));
        assert!(matches!(
            Structure.score(&d, Deadline::new(std::time::Duration::ZERO)),
            ScoreOutcome::Failed(Error::Timeout)
        ));
    }
}
