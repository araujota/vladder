## ADDED Requirements

### Requirement: Semantic recognition is token bounded
The system SHALL NOT infer a supported semantic operation from a substring embedded in an unrelated
identifier or literal.

#### Scenario: Unrelated hexadecimal seed
- **WHEN** source contains `0xC0FFEE` but no UTF-8 leading-byte predicate
- **THEN** the source is not classified as an exact UTF-8 predicate reduction

### Requirement: Physical identities are non-empty and provenance bearing
The system SHALL resolve a non-empty hot implementation from a named symbol, emitted assembly, or
method-specific LLVM IR before deduplicating physical candidates.

#### Scenario: Compiler artifact contains no resolved hot body
- **WHEN** no instruction or IR body can be associated with the candidate function
- **THEN** the identity is `unresolved`
- **AND** the candidate is not deduplicated against another unresolved candidate
- **AND** the search is not classified as bounded optimal

### Requirement: Native project context is preserved
The system SHALL compile Zig sources in their module graph and load Julia methods in their declared
project/module world.

#### Scenario: Source has relative imports or package dependencies
- **WHEN** semantic capture is requested
- **THEN** the target source remains at its original path or is loaded through its native project
- **AND** generated wrappers do not replace project-relative resolution with a detached source copy

### Requirement: Reflection does not execute arbitrary targets
The system SHALL separate compiler reflection from differential or allocation execution.

#### Scenario: Julia method has a non-byte-count signature
- **WHEN** typed and LLVM capture are requested for an exact tuple signature
- **THEN** reflection succeeds or fails based on method binding
- **AND** the target is not called with a hard-coded byte vector and needle

### Requirement: Shared bounded dataflow is natively executable
The system SHALL emit native C, C++, Zig, and Julia source for every promoted bounded-dataflow
terminal while preserving one shared semantic graph and proof vocabulary.

#### Scenario: Stable compaction is emitted in multiple languages
- **WHEN** the same contract and terminal are emitted for C, C++, Zig, and Julia
- **THEN** every candidate binds to the same language-neutral derivation
- **AND** native differential tests compare status, extent, order, and output values
- **AND** any scalarized ISA terminal is identified as physically non-distinct
