## ADDED Requirements

### Requirement: C emits authoritative v2 information flow
Every supported bounded C region SHALL emit a SemanticFlowGraph v2 while legacy family-specific
consumers continue through an explicit compatibility view.

#### Scenario: Existing C grammar consumes a migrated graph
- **WHEN** an existing pointwise, stencil, scan, recurrence, or indirect-memory test runs
- **THEN** its legacy behavior SHALL remain unchanged and its report SHALL include a valid v2 graph.

### Requirement: C++ effects use the shared schema
Bounded C++ capture SHALL represent typed ABI inputs/outputs, calls, local subregions, memory
effects, exceptional exits, ownership, synchronization, and external effects in v2.

#### Scenario: Owning C++ wrapper is not locally closed
- **WHEN** allocation, destruction, or an external call remains
- **THEN** the graph SHALL retain those typed effects and required protocol obligations without
  claiming local LLVM equivalence for the wrapper.
