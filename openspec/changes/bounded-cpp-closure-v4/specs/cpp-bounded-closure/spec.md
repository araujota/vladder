## ADDED Requirements

### Requirement: Capability-vector classification
vLadder SHALL report semantic capture, isolation, candidate generation, local proof, benchmark,
source rewrite, and remaining protocol scope independently for every selected C++ definition.

#### Scenario: Local proof without generic benchmark inputs
- **WHEN** a typed local function can be isolated and a source candidate can be generated but no
  workload adapter exists
- **THEN** local proof and source readiness SHALL be reported without claiming physical promotion

### Requirement: Whole-function proof units
vLadder SHALL emit the exact normalized compiler-lowered function as a proof unit for modeled local
functions, including aggregate returns and local object-state methods.

#### Scenario: Byte parser returning a status structure
- **WHEN** a byte-span parser has local no-unwind compiled effects and a modeled aggregate result
- **THEN** isolation SHALL emit a build-specific proof unit without inventing aggregate layout

### Requirement: Bounded loop capsules
vLadder SHALL be able to generate and compile an immediately invoked noinline lambda capsule for a
bounded nested loop whose source semantics admit capture-by-reference isolation.

#### Scenario: Typed copy loop inside an allocating wrapper
- **WHEN** allocation occurs outside a loop and the loop has no escaping control or external
  protocol operation
- **THEN** the wrapper remains protocol-scoped while the loop receives its own proof symbol

### Requirement: Typed schedule candidates
vLadder SHALL generate deterministic guarded loop-schedule candidates for automatically isolated
typed loops and SHALL emit a proof build in which the scheduling directive is absent.

#### Scenario: Unroll hint candidate
- **WHEN** a capsule loop is eligible for factor-two unrolling
- **THEN** the physical source contains the guarded hint, the proof source suppresses it, and the
  proof-unit IR matches the baseline capsule

### Requirement: Escaping-control rejection
vLadder SHALL reject automatic lambda isolation when a selected region contains control transfer
whose target is outside the region.

#### Scenario: Function return inside loop
- **WHEN** a loop contains a `return` from the owning function
- **THEN** the report SHALL classify the region as requiring a control-boundary adapter

### Requirement: Stateful promotion boundary
vLadder SHALL distinguish local object-state proof-unit extraction from proof of the owning class
invariant.

#### Scenario: Local state method
- **WHEN** a method's compiled effects are local but it accesses `this`
- **THEN** identity isolation MAY pass while nonidentity promotion remains contract-bounded on a
  declared state projection and observables

### Requirement: Scoped categorical limitations
vLadder SHALL explain non-isolatable C++ behavior using evidence, blocked claim, required adapter,
and permitted continuation rather than a global unsupported result.

#### Scenario: Vulkan protocol method
- **WHEN** a method retains Vulkan calls and synchronization
- **THEN** whole-method equivalence SHALL remain external-protocol-only while attribution, lifetime
  analysis, project measurement, and independently local regions remain permitted

### Requirement: Non-applying repository audit
The C++ audit workflow SHALL aggregate isolation, proof, candidate, benchmark, rewrite, and protocol
counts without applying generated source.

#### Scenario: NeuralFusion validation
- **WHEN** its critical-path manifest is audited
- **THEN** the report SHALL record all capability levels and `source_changes_performed: false`
