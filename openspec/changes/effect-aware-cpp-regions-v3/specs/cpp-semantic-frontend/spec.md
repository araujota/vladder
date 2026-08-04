## Purpose

Define effect-aware, typed, compositional C++ region acceptance without overstating automatic
source transformation or protocol proof.

## ADDED Requirements

### Requirement: Compiler-derived effect classification
vLadder SHALL inspect the selected function's optimized LLVM realization before classifying helper
calls, unwind behavior, allocation, synchronization, and remaining external effects.

#### Scenario: Inlined byte parser helpers
- **WHEN** source calls are fully inlined and the selected effect IR is `nounwind`, has no allocator
  or synchronization operations, and contains no unmodeled remaining calls
- **THEN** those source calls SHALL NOT independently force an external-call adapter

### Requirement: Typed C++ ABI descriptors
vLadder SHALL describe scalar, pointer, span, borrowed vector, structured reference, callable, and
aggregate-return boundaries with element type, mutability, ownership, and lowered ABI evidence.

#### Scenario: Byte span with aggregate result
- **WHEN** a selected function consumes `std::span<const std::byte>` and Clang lowers its aggregate
  result to explicit `sret` storage
- **THEN** the report SHALL classify both boundaries without a float-only ABI rejection

### Requirement: Support-tier separation
vLadder SHALL separately report semantic acceptance, source-transformation readiness, proof
classification, and claim boundary.

#### Scenario: Local IR without a source lowerer
- **WHEN** a function is a bounded local compiled region but no deterministic source lowerer exists
- **THEN** it MAY be accepted as `whole_function_local_ir` but SHALL NOT enter candidate optimization
  or emit a replacement

### Requirement: Bounded subregion discovery
vLadder SHALL enumerate bounded loop or compound-region candidates inside owning C++ definitions
and identify source range, local calls, explicit hazards, and required proof boundary.

#### Scenario: Loop inside an allocating wrapper
- **WHEN** an owning function contains a loop with no allocation, external call, synchronization,
  throw, or object-state access inside the loop
- **THEN** the whole function remains adapter-bound while the loop is reported as an extractable
  subregion candidate

### Requirement: Effect-aware ownership and exception handling
vLadder SHALL distinguish trivial constructions and compiler-proven no-unwind behavior from actual
allocation, destruction, and exception protocols.

#### Scenario: Non-noexcept pure function
- **WHEN** a function is not spelled `noexcept` but its selected effect IR is `nounwind` and contains
  no explicit throw or unwind operations
- **THEN** source spelling alone SHALL NOT force an exception adapter

### Requirement: Compositional proof envelopes
vLadder SHALL emit explicit obligations for ABI mapping, extents, aliasing, aggregate layout,
container capacity, object-state projection, external models, and verifier selection.

#### Scenario: Structured local region
- **WHEN** a structured C++ boundary is semantically accepted
- **THEN** its proof plan SHALL state what Alive2, Z3, CBMC, differential testing, and project tests
  do and do not establish

### Requirement: Inspection-matrix audit
vLadder SHALL aggregate multiple C++ inspection reports by support tier and adapter kind without
running optimization or applying source changes.

#### Scenario: Repository acceptance corpus
- **WHEN** an audit manifest names many source/function/symbol targets
- **THEN** vLadder emits deterministic per-region reports and aggregate counts suitable for release
  regression testing

### Requirement: External protocol honesty
vLadder SHALL retain external protocol adapters for remaining syscalls, Vulkan/OpenUSD operations,
callbacks, synchronization, and owning publication or retirement behavior.

#### Scenario: Vulkan method with local arithmetic
- **WHEN** a method includes both local arithmetic and Vulkan calls
- **THEN** local subregions MAY be identified but the complete method SHALL NOT receive a local
  Alive2 equivalence claim
