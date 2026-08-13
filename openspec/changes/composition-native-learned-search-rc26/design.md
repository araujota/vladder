# Design

## Native Trace Authority

The enumerator emits a `composition-native-search-trace-v1` artifact. Each state carries its exact
canonical semantic hash, ordered action history, semantic graph, contracts, ownership/lifetime
state, and measured expansion cost. Each frontier records all legal siblings together, the exact or
symbolically previewed child delta, and an explicit optimization-interaction graph. Outcomes are
attached only after exhaustive terminal evaluation.

RC24/v3 branch data remains valid for encoder pretraining and auxiliary tasks. Reconstructed Phase-A
decisions are not composition-native labels and cannot satisfy the new campaign gates.

## Interaction Representation

The interaction graph has typed semantic-owner, representation, lifetime, authority, transformation,
contract, materialization, memory, and cross-TU nodes. Symbolically known relations are explicit.
Higher-order interactions use factor nodes so ordinary graph tooling can represent multi-action
enablement and conflict without a separate hypergraph runtime.

## Exact Reduction

Semantic-state canonicalization precedes learned scoring. Exact hash aliases are transpositions.
Learned equivalence, commutativity, or dominance outputs are proposals sent to deterministic and
formal checkers. Their accepted reductions are measured separately from learned ordering.

## Learning

The policy receives the parent semantic graph, interaction graph, ordered action history, sibling
set, and action-specific state delta. Project and source-language identity are excluded. Primary
supervision is listwise sibling advantage; tier, distance, cost, and verified-equivalence predictions
are auxiliary. Required controlled variants cover dual GPS, heterogeneous local/global attention,
and factor-node encoding at 1-5M parameters.

## Evaluation

Leave-one-project-out online replay exposes a frontier only when its parent is expanded. Recovery is
weighted by actual construction/proof/compiler/benchmark cost where captured, with expansion count
reported as a fallback dimension. Useful, proof-valid distinct, material, and retained terminals are
reported independently. Exact reductions, learned ordering, and post-search oracle results remain
separate.
