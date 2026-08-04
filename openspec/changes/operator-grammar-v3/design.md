# Design: Operator Grammar And Search V3

Each rule declares an input subgraph, replacement, contract predicates, proof
schema, estimated cost delta, and source-lowering capability. Local equivalence
regions use bounded saturation. A deterministic beam composes regional choices
and removes candidates dominated on legality, traffic, code size, stack, and
static latency. Search logs every expansion and rejection.

The source lifter consumes the selected OperatorGraph plus schedule; it never
recovers semantics from a candidate name. An optional untrusted LLM may format
or propose source but remains behind the V2 zero-trust admission boundary.
