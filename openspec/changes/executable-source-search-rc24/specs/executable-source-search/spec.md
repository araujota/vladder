## ADDED Requirements

### Requirement: Source-route claims are stage specific
The system SHALL report recognition, contract inference, applicability, enumeration, emission,
compilation, proof, identity, and source reconstruction independently for every grammar family.

#### Scenario: Specialist API exists but source binding does not
- **WHEN** a grammar rule has a callable specialist backend but the extracted root lacks its input contract
- **THEN** the rule is classified as `contract_blocked` or `binding_missing`
- **AND** it is not counted as executable source coverage

### Requirement: Bounded searches emit complete lineage
The system SHALL emit every family, parameter, candidate, and composition branch reached by an
authoritative bounded search into the v3 lineage contract.

#### Scenario: Useful composed descendant
- **WHEN** a terminal composition is proof-valid and physically distinct
- **THEN** every required ancestor is labeled `KEEP`
- **AND** no intermediate branch is labeled from its terminal-local outcome alone

### Requirement: Expansion is lazy and policy-interleaved
The system SHALL ask the active search policy about each partial and terminal candidate state before
generating descendants or expensive source/proof/compile artifacts and SHALL NOT require eager
materialization of the full candidate cross-product.

#### Scenario: Low-value partial composition
- **WHEN** a partial state is legal, nonduplicate, and not deterministically dominated
- **THEN** the policy may return `EXPAND`, `DEFER`, or `PRUNE`
- **AND** a live heuristic prune is recorded but does not become authoritative negative supervision

#### Scenario: Exhaustive shadow replay
- **WHEN** a bounded root is selected for training capture
- **THEN** shadow policy expands every legal nonduplicate partial state
- **AND** the resulting complete lineage supplies descendant-utility labels

### Requirement: Pruning decisions observe the canonical partial realization
The system SHALL present the same source-free, pre-decision semantic context during exhaustive
training capture and live model-guided search. That context SHALL include the selected bounded
region, the canonical partial realization, the proposed semantic delta, and the action lineage.

#### Scenario: Two schedules lower differently in one selected region
- **WHEN** the policy evaluates a schedule action for one region in a multi-region source root
- **THEN** its decision graph identifies that region's control, memory, ownership, and proof shape
- **AND** represents all already selected transformations in the partial realization
- **AND** does not expose proof, compilation, assembly, benchmark, or terminal-outcome evidence

#### Scenario: Training and live serving parity
- **WHEN** an authoritative v3 branch is replayed through the live oracle encoder
- **THEN** the canonical decision graph and focused node set are identical to the training example
- **AND** missing legacy context is explicitly classified `root_only` rather than presented as full coverage

### Requirement: Automatic family dispatch is a live lazy decision
The system SHALL expose independently classified grammar families as the first lazy search layer
for automatic source searches and SHALL NOT select one matching family before policy evaluation.

#### Scenario: Multiple applicable source families
- **WHEN** one semantic root satisfies more than one bounded family contract
- **THEN** every applicable family is represented as a sibling lazy branch
- **AND** expanding one family does not materialize descendants from another family

#### Scenario: Family prune
- **WHEN** the live policy prunes an applicable grammar-family branch
- **THEN** no source candidate, proof call, or compiler invocation for that family occurs
- **AND** the prune remains non-authoritative supervision until an exhaustive shadow run closes it

### Requirement: Negative supervision has closure authority
The system SHALL produce pruning supervision only from exhaustive finite enumeration or a registered
sound contract, legality, or dominance proof.

#### Scenario: Missing alias declaration
- **WHEN** a transformation requires disjoint ranges and aliasing is unresolved
- **THEN** the branch remains `KEEP_UNCERTAIN` or `BLOCKED_BY_CONTRACT`
- **AND** absence of generated candidates is not treated as a negative search result

#### Scenario: Deterministic branch is outside the learned decision surface
- **WHEN** sound legality rejects a state or canonical identity memoizes it before policy evaluation
- **THEN** v3 retains the branch and authority for audit
- **AND** model training and pruning metrics exclude it from learned-policy examples

### Requirement: Common bounded contracts are inferred conservatively
The system SHALL infer contracts from compiler-visible signatures, effects, constants, and guards,
while retaining unresolved semantic assumptions explicitly.

#### Scenario: Caller-owned no-growth output
- **WHEN** a bounded output span and dominating capacity guard are captured
- **THEN** stable compaction candidates may be enumerated
- **AND** allocation, exception, aliasing, and output atomicity obligations remain explicit

#### Scenario: Runtime-sized borrowed C++ range
- **WHEN** the selected function accepts a compiler-modeled borrowed contiguous range with a runtime extent
- **THEN** the contract records a runtime-sized extent rather than inventing a source maximum
- **AND** arbitrary-length correctness is reduced to a proved finite block plus an ordered composition obligation

#### Scenario: Capacity preflight uses input extent
- **WHEN** the original C++ wrapper rejects before writing because input size exceeds spare capacity
- **THEN** generated candidates preserve that exact guard and unchanged-output behavior
- **AND** they do not substitute a selected-output-count guard

#### Scenario: Aliasing is not statically disjoint
- **WHEN** borrowed input and output storage may overlap
- **THEN** a transformed path executes only under a complete byte-range non-overlap guard
- **AND** the overlap path preserves baseline read/write order

### Requirement: Proof-unit execution and source replacement are distinct claims
The system SHALL report bounded helper execution separately from complete compiler-selected source
reconstruction.

#### Scenario: No-growth vector wrapper around a canonical compaction
- **WHEN** vLadder proves and compiles the canonical pointer/extent kernel but has not reconstructed vector size, lifetime, and return-value behavior
- **THEN** closure is `proof_unit_only`
- **AND** the candidate remains useful search evidence without being presented as an apply-ready patch

#### Scenario: Exact free-function ABI
- **WHEN** the compiler-selected C++ definition exactly matches a supported bounded compaction or codec ABI
- **THEN** every proved terminal may replace the complete selected definition
- **AND** it is compiled with the selected production command
- **AND** closure is `replacement_ready` only after every terminal reaches a resolved source-composition disposition

### Requirement: Structured dataflow choices produce composition lineage
The system SHALL expose intermediate information-flow choices as lazy branches before concrete
realizations.

#### Scenario: Mask-driven stable compaction
- **WHEN** a mask-and-scatter branch expands into scalar-word, AVX2, and AVX-512 realizations
- **THEN** the mask-and-scatter branch is the parent of those terminals in v3 lineage
- **AND** a useful terminal marks that ancestor `KEEP`
- **AND** an exhaustive terminal set with no useful descendant marks it `PRUNE_HIGH_CONFIDENCE`

### Requirement: Searches are reproducible and resumable
The system SHALL key compilation and proof artifacts by semantic, grammar, candidate, compiler,
target, and proof-policy identities and SHALL emit deterministic results under parallel execution.

#### Scenario: Repeated unchanged root
- **WHEN** an identical root is searched again on the same target and policy
- **THEN** immutable compile/proof entries are reused
- **AND** emitted branch and observation identities remain unchanged

#### Scenario: Campaign interruption after completed roots
- **WHEN** one or more roots complete before a later root or process is interrupted
- **THEN** each completed root already has a schema-validated v3 bundle
- **AND** a progress artifact identifies admitted records without requiring campaign completion

#### Scenario: Candidate-dense regional Cartesian product
- **WHEN** exhaustive shadow search reaches many independent concrete terminals
- **THEN** terminal proof and compilation MAY execute in parallel after lineage enumeration
- **AND** result ordering, candidate identity, proof inputs, deduplication, and propagated labels remain deterministic
- **AND** every terminal in the declared finite domain is still resolved or explicitly left open

### Requirement: Canonical bounded regions share executable semantics across languages
The system SHALL lower supported bounded C, C++, Rust, Zig, and Julia regions from one canonical
semantic grammar while preserving native signatures, compiler corroboration, and language-specific
source realization.

#### Scenario: Equivalent pointwise roots in different languages
- **WHEN** native compiler evidence corroborates the same canonical information-flow region
- **THEN** each language exposes the same grammar derivations and typed action lineage
- **AND** generated source is compiled and differentially checked through that language's native toolchain
- **AND** local-region closure is not promoted to owning-wrapper equivalence

### Requirement: Arbitrary external semantics fail closed without blocking local search
The system SHALL isolate closed local descendants while representing ownership, concurrency, GPU,
network, driver, and external-library behavior as explicit protocol boundaries.

#### Scenario: Local codec inside an owning network method
- **WHEN** packet emission is external but the codec has exact bounded inputs and outputs
- **THEN** codec descendants remain executable and provable
- **AND** whole-method equivalence remains excluded until its protocol adapter is supplied

### Requirement: Compiler-selected functions remain executable beyond source capsules
The system SHALL admit finite selected-function LLVM pipelines from a production compilation
unit when the selected symbol and complete module context are available. It SHALL preserve named
aggregate types, declarations, globals, and personality context, validate the same-named function
with Alive2's two-module interface, lower every candidate to target assembly, and deduplicate the
selected symbol.

#### Scenario: Aggregate-result C++ function
- **WHEN** a selected function returns a lowered aggregate that cannot be represented by a
  concatenated isolated-function proof file
- **THEN** candidate pipelines retain the complete extracted LLVM module
- **AND** proof-unavailable constructs such as unsupported interprocedural `invoke` remain
  uncertain terminal outcomes rather than pruning negatives

### Requirement: Effect-preserving schedules do not overclaim C++ closure
The system SHALL distinguish a locally closed proof capsule from an ordinary compiler scheduling
request inserted into an unchanged owning function. Non-assumptive unroll, vector-width, and
interleave requests MAY be enumerated for loops containing ownership, callbacks, exceptions,
atomics, or external calls when Clang retains legality authority and the source range is valid.

#### Scenario: Callback loop
- **WHEN** a loop invokes an opaque callback but has a valid selected-build source range
- **THEN** local capsule eligibility remains false and the callback protocol remains explicit
- **AND** guarded schedule candidates may compile, retain the owning body unchanged, and carry a
  compiler-legality schedule proof class
