# Research note: building auditable AI-text detectors

Source: Liam Dugan, Callum McDougall, Matthew Denton, Phillip Pham, Christine
Kaeser-Chen, and Chris Callison-Burch. "Building Auditable AI Text Detectors with
Sparse Autoencoders." EMNLP 2026, pages 17640–17689.
<https://aclanthology.org/2026.emnlp-main.762.pdf>.

The supplied local PDF `~/Downloads/building-auditable.pdf` has SHA-256
`426e3c20b85f56627912e82731559e6f9d9656546768ddaf60652469db6702d8`. The
supervisor directly verified that this hash matches the downloaded ACL PDF at
the URL above. The extracted text used for this note is
`/tmp/nobotrs-building-auditable-user.txt` (SHA-256
`a1af5c110106e907b1301cb2206ba324e2442b3da0bc9ccbb6f5c775c1c5b0ce`). This note
is outside the imported research originals and corrects no upstream files.

## Lessons relevant to nobotrs

1. **Explanations need hard negatives and context-dependence checks.** The
   paper's limitation section says auto-interpretation descriptions are biased
   toward recall and low precision: a feature that fires on "Tom" only after
   "Hello" can receive a perfect simulation score while the description misses
   the dependency. It recommends better hard-negative sampling and synthetic
   data. For nobotrs, a called-out phrase is not sufficient evidence that the
   phrase is the operative signal; fixtures must include the same surface form in
   benign contexts and hard negatives that do not trigger the rule.

2. **Targeted ablation should check collateral signals.** Section 7 ablates a
   feature's explanation and compares the targeted logit change with the change
   in non-targeted features; Table 3 reports normalized activation shifts for
   both targeted and non-targeted features plus sign agreement. The document-level
   paraphrase ablation then checks whether removing the listed features flips the
   prediction without revealing new ones. For a rule-based detector, the analogue
   is to disable one rule at a time, confirm the intended occurrence disappears,
   and measure whether other families, overlap selection, or document metrics
   change collaterally.

3. **OOD model/domain slices and low-FPR behavior belong in evaluation.** Table 1
   reports in-distribution and out-of-distribution COLING/RAID performance,
   including TPR at 5% FPR; Figure 4 tracks TPR at FPR = 5% across interpretability
   thresholds. Section 6 warns that near-perfect PRDB performance suggests
   confounds or spurious features. A detector that looks strong on one domain or
   generator must be reported with domain/model slices and false-positive rates,
   not one aggregate accuracy number.

4. **Table 4 signals are domain-specific hypotheses, not default rules.** Table 4
   is explicitly PRDB peer-review data with `τ > 0.85`; its top features include
   "potential", "thorough", double colons after bolded headers, parentheses in
   question lists, and bracket characters. Section 8 says these highly specific
   token/formatting features may fail to generalize, that near-perfect PRDB
   detection may use domain shortcuts, and that whether formatting is spurious
   depends on context. These are hypotheses to test on varied domains, not
   justified default nobotrs rules. "Potential", "thorough", and formatting
   characters should not be promoted to default voting signals from this paper
   alone.

## Scope and deferred work

SAE training, model inspection, interpretability thresholds, and neural detector
comparisons are explicitly deferred. nobotrs remains an uncalibrated heuristic
linter/detector; this note does not justify new thresholds, probabilities, or
authorship claims. It supports the evaluation protocol's hard-negative,
ablation/collateral-change, OOD-slice, and low-FPR requirements.
