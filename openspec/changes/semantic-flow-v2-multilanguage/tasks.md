## 1. SemanticFlowGraph V2

- [x] 1.1 Add typed obligations, effects, protocol transitions, claims, validation, and deterministic hashing.
- [x] 1.2 Convert all current shared-graph producers from string obligations to typed obligations.
- [x] 1.3 Preserve deterministic compatibility loading for v1 producers and artifacts.

## 2. C And C++ Migration

- [x] 2.1 Attach an authoritative v2 graph to every supported legacy C `FlowGraph`.
- [x] 2.2 Replace the coarse C++ information-flow dictionary with a v2 graph and compatibility aliases.
- [x] 2.3 Test typed ownership, exception, synchronization, allocation, and external-call effects.

## 3. Complete Deep Grammar Emitters

- [x] 3.1 Add native C++ emission and same-executable compilation for every terminal realization.
- [x] 3.2 Add native Zig emission and same-executable compilation for every terminal realization.
- [x] 3.3 Add native Julia emission and warmed same-process differential/physical execution for every terminal realization.
- [x] 3.4 Extend source reconstruction and proof binding to all five languages.

## 4. Product And Validation

- [x] 4.1 Test cross-language semantic-shape identity and typed-obligation completeness.
- [x] 4.2 Update README, architecture, skill, grammar metadata, and release identity.
- [x] 4.3 Run strict OpenSpec validation, full regression, package audit/install smoke, and resident refresh.
