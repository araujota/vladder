## Purpose

Define direct, fail-closed C++ extraction and verified kernel isolation for vLadder.

## ADDED Requirements

### Requirement: Compilation-database fidelity
vLadder SHALL parse one exact compilation-database entry and preserve the semantic compiler flags
used to instantiate and type-check the target translation unit.

#### Scenario: Ambiguous source commands
- **WHEN** two materially different commands compile the same source and no command index is given
- **THEN** extraction fails with a compilation-command selection requirement

### Requirement: Semantic C++ target selection
vLadder SHALL use Clang AST declarations and mangled symbols to select a concrete definition.

#### Scenario: Overloaded method
- **WHEN** a source name resolves to more than one definition
- **THEN** no region is isolated until the caller supplies the concrete symbol

### Requirement: Bounded kernel isolation
vLadder SHALL isolate supported pointer and `std::span<float>` loops into the canonical C kernel
grammar without changing expression or iteration order.

#### Scenario: Span map
- **WHEN** a `noexcept` span function has a proved destination-extent precondition and one admitted
  loop
- **THEN** vLadder emits a canonical C kernel and a compilable C++ realization

### Requirement: Layered proof classification
vLadder SHALL distinguish local kernel refinement from adapter and owning-protocol verification.

#### Scenario: Isolated kernel proof
- **WHEN** Alive2 validates the generated C kernel
- **THEN** the report may claim local kernel refinement but SHALL NOT claim whole-method C++
  equivalence solely from that result

### Requirement: Explicit unsupported semantics
vLadder SHALL emit typed adapter obligations for owning or protocol-bearing C++ semantics.

#### Scenario: RAII and external API method
- **WHEN** the target constructs an owning object or calls an unmodeled API
- **THEN** the report identifies ownership and external-call adapters and emits no replacement
