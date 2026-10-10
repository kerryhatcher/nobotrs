# Stable rule catalog

Dictionary version: 2026.07.26. All vocabulary matches are medium severity editing prompts, with uncalibrated family thresholds. English vocabulary matching uses ASCII case folding; boundaries use Unicode alphanumeric characters plus underscore.

| Rule ID | Pattern | Matching |
|---|---|---|
| `delve` | `delve` | exact |
| `tapestry` | `tapestry` | exact |
| `multifaceted` | `multifaceted` | exact |
| `nuanced` | `nuanced` | exact |
| `leverage` | `leverage` | exact |
| `utilize` | `utilize` | exact |
| `seamless` | `seamless` | exact |
| `foster` | `foster` | exact |
| `pivotal` | `pivotal` | exact |
| `paramount` | `paramount` | exact |
| `holistic` | `holistic` | exact |
| `streamline` | `streamline` | exact |
| `transformative` | `transformative` | exact |
| `meticulous` | `meticulous` | exact |
| `intricate` | `intricate` | exact |
| `embark` | `embark` | exact |
| `beacon` | `beacon` | exact |
| `testament` | `testament` | exact |
| `plethora` | `plethora` | exact |
| `myriad` | `myriad` | exact |
| `moreover` | `moreover` | exact |
| `furthermore` | `furthermore` | exact |
| `nevertheless` | `nevertheless` | exact |
| `underscore` | `underscores` | exact |
| `showcase` | `showcase` | exact |
| `emphasize` | `emphasize` | exact |
| `facilitate` | `facilitate` | exact |
| `empower` | `empower` | exact |
| `robust` | `robust` | exact |
| `cutting-edge` | `cutting-edge` | exact |
| `paradigm-shift` | `paradigm shift` | exact |
| `harness-verb` | `harness` | exact |
| `not-just-x-but-y` | `it'?s not just [a-z ]+, it'?s` | regex |
| `important-to-note` | `it is important to note that` | regex |
| `rapidly-evolving` | `in today'?s rapidly evolving` | regex |
| `cannot-be-overstated` | `cannot be overstated` | regex |
| `embark-on-a-journey` | `embark on a journey` | regex |
| `a-testament-to` | `a testament to` | regex |
| `plays-a-role` | `plays a (crucial&#124;vital&#124;pivotal) role` | regex |
| `worth-noting` | `it'?s worth noting` | regex |
| `heres-the-thing` | `here'?s the thing` | regex |
| `let-me-be-clear` | `let me be clear` | regex |
| `uncomfortable-truth` | `the uncomfortable truth is` | regex |
| `experts-agree` | `experts agree` | regex |
| `studies-show` | `studies show` | regex |
| `thats-it-thats-the-x` | `that'?s it, that'?s the [a-z ]+` | regex |

`punctuation.em-dash-density`: medium severity, localized occurrences with a document-density heuristic. `statistics.burstiness`: low severity, document-wide sentence-length variation; has no invented source location. Readability, MTLD, compression and entropy remain informational metrics without actionable rules or votes.

Exact patterns enumerate overlapping candidates before Unicode boundary checks. Regex rules enumerate distinct starting positions but use the Rust regex leftmost-first alternation at each start; alternatives at the same start are not an exhaustive language enumeration. Empty patterns, duplicate IDs and non-vocabulary dictionary families are rejected. Regex compilation is limited to 64 KiB per expression.
