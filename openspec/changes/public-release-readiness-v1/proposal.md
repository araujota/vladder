# Public Release Readiness v1

## Why

vLadder has a substantial proof-gated optimization engine, but a broad open-source release also
requires a stable user contract: installation, supported Linux identity, reproducible examples,
artifact schemas, privacy defaults, contribution guidance, security CI, and a review/download
surface. Those release concerns must be tested rather than inferred from the engine test suite.

## What Changes

- Add a versioned artifact-schema registry and schema validation CLI.
- Make local-only processing and explicit review-upload consent executable policy.
- Add a canonical agent-review prompt, strict record format, and optional Convex persistence.
- Add a cohesive three-demo runner and preserve the NeuralFusion case-study evidence boundary.
- Add grammar-authoring, proof-boundary, benchmark-reproducibility, roadmap, and contribution docs.
- Add Linux install/container smoke checks and seeded good/bad transformation CI.
- Add Ruff, Bandit, SonarCloud, and Snyk release workflows with explicit external-secret gates.
- Add a small release website exposing current support, install commands, docs, and downloads.

## Non-Goals

- Uploading source, traces, proofs, or benchmark artifacts by default.
- Treating a website build or review submission as optimization evidence.
- Claiming arbitrary C++, cross-platform, or whole-device equivalence.
- Making external SaaS credentials a prerequisite for local optimization.
