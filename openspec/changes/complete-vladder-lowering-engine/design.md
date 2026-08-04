## Context

vLadder has mature but separate expression, operator, pipeline, projection, Q4_K, and traversal
search implementations. The release capability registry provides a useful cross-cutting
vocabulary, but its lowerer names are not symbols that can be imported or invoked. A generalized
engine needs a stable intermediate result before it can safely unify source generation.

## Goals / Non-Goals

**Goals:**

- Make every registry rule resolve to executable Python code.
- Produce a deterministic, machine-readable lowering plan containing guards, IR operations,
  proof obligations, cost signals, backend route, and derivation identity.
- Distinguish planning support from C/C++ source-emission support.
- Connect source-capable families to existing specialized engines without duplicating them.
- Make completeness testable at package build and installation time.

**Non-Goals:**

- Pretend that a plan is generated C/C++.
- Parse or rewrite arbitrary whole-program C++ in this change.
- Make approximate, concurrency, or ABI-changing transformations promotable without their
  required contract and proof adapters.
- Replace existing workload-specific search implementations.

## Decisions

### 1. Use one concrete lowerer per grammar family

Each family declares an importable `module:class` entrypoint. The class owns exactly one family
and must report exactly the rule IDs declared by that family. Registry validation imports and
instantiates it, preventing symbolic placeholders from passing release validation.

### 2. Make plan lowering the universal executable contract

Every rule lowers into ordered information-flow operations plus legality guards, proof
obligations, cost objectives, and an optional specialized backend route. This is useful to search
planning and agents even when generic source reconstruction is not implemented.

### 3. Treat source emission as a separate capability

Rules declare `plan`, `specialized`, or `generic` emission maturity. `plan` rules produce no
source and fail a source-emission request. `specialized` rules identify a concrete existing
backend and its required input shape. `generic` is reserved for a backend that directly emits
source through this interface.

### 4. Keep legality data explicit

Each rule declares required contract facts and parameters. Missing inputs return a structured
`rejected` result before search or benchmarking. Plans preserve semantic risks and proof methods
from the family registry.

### 5. Hash the complete derivation

The plan ID hashes grammar identity, family, rule, normalized contract facts, parameters, input
identity, and lowering operations. Repeated requests are byte-for-byte deterministic.

## Risks / Trade-offs

- A universal planning layer may appear more capable than source generation. Mitigation: expose
  separate plan and source coverage and reject unsupported emission requests.
- Specialized backend signatures differ. Mitigation: initially emit typed backend routes and
  invocation requirements; adapt execution incrementally behind the stable plan contract.
- Import validation can make registry loading stricter. Mitigation: produce precise family and
  entrypoint diagnostics and test wheel installation.
