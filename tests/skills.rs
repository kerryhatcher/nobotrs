// Cargo package tests run these same checks from the extracted archive.
const DRAFT: &str = include_str!("../skills/humanize-writing/SKILL.md");
const REVISE: &str = include_str!("../skills/review-writing/SKILL.md");
const BRIEF: &str = include_str!("../guidance/brief.md");

#[test]
fn installed_skills_ship_the_canonical_offline_brief() {
    for (name, skill, brief) in [
        (
            "humanize-writing",
            DRAFT,
            include_str!("../skills/humanize-writing/references/writing-brief.md"),
        ),
        (
            "review-writing",
            REVISE,
            include_str!("../skills/review-writing/references/writing-brief.md"),
        ),
    ] {
        assert!(skill.starts_with(&format!("---\nname: {name}\ndescription: ")));
        assert!(skill.contains("(references/writing-brief.md)"));
        assert_eq!(brief, BRIEF);
        assert!(skill.contains("nobotrs review") && skill.contains("nobotrs compare"));
    }
}
#[test]
fn revision_and_drafting_have_the_same_stopping_rule() {
    let stop = |text: &'static str| text.split_once("## When to stop\n").unwrap().1.trim();
    assert_eq!(stop(DRAFT), stop(REVISE));
    assert!(stop(DRAFT).contains("author-approved"));
}
