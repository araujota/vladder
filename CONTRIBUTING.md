# Contributing To vLadder

Start with an issue describing the measured workload, semantic boundary, and intended evidence.
Changes that widen a proof or performance claim require tests that fail before the change.

## Contribution Matrix

| Background | Useful contributions | Required evidence |
|---|---|---|
| New user | install reports, demo failures, documentation clarity | OS/tool versions and exact command |
| Technical writer | tutorials, glossary, claim-boundary examples | links and command validation |
| Application developer | workload adapters, observable oracles, case studies | pinned revision, contract, raw samples |
| Performance engineer | attribution, counters, benchmark harnesses | hardware manifest and reproducibility bundle |
| Compiler engineer | extraction, canonicalization, source lowerers | IR/source binding and good/bad tests |
| Formal methods engineer | Z3/Alive2/protocol obligations | explicit theorem scope and counterexample test |
| Language specialist | native frontend/emitters | language semantics, build identity, differential tests |
| Security reviewer | threat model, Bandit/Snyk/Sonar findings | reproducible finding and bounded remediation |
| UI contributor | release site, artifact browser, accessibility | production build and responsive browser checks |

Non-experts do not need to author solvers. Reproducing a failed install, improving an error message,
adding a malformed-artifact fixture, or documenting a negative result is valuable.

## Pull Requests

Run the focused tests, `python scripts/validate_release_seeds.py`, `ruff check`, `bandit`, and the
public release gate. Do not include project source, models, benchmark dumps, credentials, or
generated build directories. Preserve local-only behavior unless a network action is explicitly
named and consent-gated.
