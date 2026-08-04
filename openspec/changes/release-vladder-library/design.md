## Context

The repository contains a working Python optimizer, multiple generations of operator and
production-kernel research, machine-readable grammars, and layered proof helpers. The CLI is the
only public facade, package metadata omits runtime dependencies, proof strictness is opt-in, and
the tree also contains generated outputs and a large vendored llama.cpp checkout. See
`proposal.md` for the release motivation and the four capability specs for observable behavior.

The release must remain useful on ordinary bounded C/C++ regions while preserving specialized
operator and quantized-kernel modules as optional advanced capabilities. It cannot imply that
all modeled grammar families already have executable lowerings or complete formal proofs.

## Goals / Non-Goals

**Goals:**

- Establish one stable identity, package, CLI, artifact schema, and Python facade.
- Make grammar coverage and implementation maturity inspectable rather than implicit.
- Encode a strict promotion policy that distinguishes proof from testing and unavailable from
  passing.
- Keep installation reproducible on Ubuntu while allowing an existing compatible LLVM/Alive2
  toolchain to be reused.
- Package a concise agent skill whose process forces attribution and proof before source changes.
- Validate the built distribution from an isolated environment against an external workspace.

**Non-Goals:**

- Reimplement all historical research modules or claim every declared grammar family is lowered.
- Bundle LLVM, Alive2, Linux perf, llama.cpp, models, or benchmark output inside the wheel.
- Treat randomized differential tests as universal equivalence proofs.
- Automatically apply a patch when no statistically meaningful verified winner exists.
- Guarantee identical benchmark values across different hardware or thermal configurations.

## Decisions

### 1. Rename in place and retain a bounded compatibility command

The Python source package becomes `vladder`; internal imports and output defaults follow the new
name. The distribution exports `vladder` as primary and a deprecated `silicontune` console alias
for one release so existing experiment scripts do not become unusable. New documentation and
artifacts use only vLadder terminology except a migration note.

Alternative: wrap the old package from a new package. Rejected because two package namespaces
would let identity and resources drift and would complicate source distribution audits.

### 2. Add a thin typed facade over the existing CLI engine

`vladder.api` defines immutable request, verification-policy, benchmark-policy, and result types.
The existing command engine remains the implementation initially, invoked through an explicit
argument translation layer. This preserves one behavior path while allowing embedding without
shelling out. Result loading validates the report schema and derives promotability from proof and
measurement fields.

Alternative: immediately decompose the large CLI into services. Deferred because it increases
release risk without changing behavior; modularization can follow once the facade is stable.

### 3. Publish a capability registry separate from executable grammar files

`grammars/vladder-v1/capabilities.json` is the authoritative inventory. Each family declares
status (`operational`, `experimental`, `modeled`, or `research`), rules, contract facts, proof
strategies, cost signals, and lowerer identifiers. Existing per-shape and higher-level grammars
remain executable resources. Registry validation ensures unique identifiers, known status values,
required fields, and a stable content hash.

This distinction prevents breadth of representation from being confused with breadth of current
synthesis. A modeled C++ memory-order transformation is expressible and auditable but cannot be
selected until an executable lowerer and verification path are registered.

### 4. Use verification policies, not a single proof boolean

The facade offers `strict`, `balanced`, and `exploratory` policies. Strict promotion requires
structural and memory legality, a successful schema/SMT proof, Alive2 correctness for supported
IR, differential tests, and a measured minimum effect. Unsupported Alive2 semantics fail strict
promotion but remain explicit evidence in non-promoting exploratory runs. Proof artifacts retain
tool versions, assumptions, bounds, and logs.

Alive2 remains translation validation between compiled reference and candidate functions; Z3
handles explicit bit-vector, arithmetic, and bounded pointer-footprint obligations. Neither is
described as a whole-C proof when language or environment semantics are outside its model.

### 5. Install external tools through a staged, idempotent installer

`scripts/install.sh` supports `--prefix`, `--skill-dir`, `--with-alive2`, `--no-system-packages`,
and `--dry-run`. It installs Ubuntu packages when permitted, creates an isolated virtual
environment, installs the built package, installs/validates the skill, and runs `vladder doctor
--strict`. Alive2 is either reused from `PATH` or built at a pinned revision compatible with the
detected LLVM major; its build is optional for basic install but required by strict proof runs.

Alternative: declare system tools as Python dependencies. Rejected because pip cannot reliably
install a compatible compiler, perf subsystem, or Alive2 binary.

### 6. Make release hygiene testable

Build metadata includes only the `vladder` package, grammar resources, skill, examples, and core
docs. `.gitignore`, package-data rules, and `scripts/audit_release.py` reject caches, generated
output patterns, models, credentials, nested VCS directories, and oversized vendored trees.
Historical OpenSpec records can remain in source control but are not wheel data.

### 7. Treat the NeuralFusion run as a release evaluation, not guaranteed patch production

The installed package is invoked from an isolated prefix. The skill process first profiles or
uses existing attribution to select a bounded C/C++ target, extracts a reproducible optimization
case, runs the graph search and proof policy, benchmarks on the same host, and applies nothing
unless promotion gates pass. A JSON report records both positive and negative outcomes.

## Risks / Trade-offs

- [Alive2 version mismatch with Clang IR] -> Pin compatible major versions, report both versions,
  sanitize only known attributes, and fail strict checks on unsupported IR.
- [A broad registry overstates implementation] -> Require explicit maturity and lowerer fields;
  reject modeled-only rules at execution time.
- [Facade delegates to argparse internals] -> Keep the translation isolated and cover it with API
  tests; refactor internals after release compatibility is established.
- [System package installation requires privileges] -> Support reuse-only and no-system-package
  modes, dry-run command planning, and user-selected prefixes.
- [Benchmark noise creates false promotion] -> Preserve CPU affinity, independent repetitions,
  confidence intervals, baseline inclusion, and a minimum effect threshold.
- [Tree trimming removes useful evidence] -> Delete generated and vendored residue only after
  preserving release-relevant schemas, summaries, examples, and test fixtures.
- [C++ semantics exceed current extractor] -> Represent requirements in the registry but report
  unsupported lowering; use bounded extracted C-compatible regions until C++ extraction matures.

## Migration Plan

1. Complete and validate the OpenSpec release change.
2. Rename the package and internal references, add the primary CLI, compatibility alias, facade,
   registry, doctor command, installer, audit, and skill.
3. Update tests, examples, and documentation; retain historical OpenSpec prose as provenance.
4. Remove generated outputs, caches, and vendored application content from the release tree.
5. Build sdist and wheel, audit both, install into a clean prefix, and run unit plus CLI tests.
6. Install the skill into an isolated agent home and execute the NeuralFusion dry run.
7. If a blocking regression appears, restore the last source snapshot and keep the OpenSpec
   change open; no external package publication occurs in this task.
