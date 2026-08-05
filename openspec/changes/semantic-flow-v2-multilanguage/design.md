## Architecture

`SemanticFlowGraph` remains the common computational graph. Version 2 adds three typed planes:

1. `SemanticObligation`: a stable identifier, category, scope, statement, proof method, and native
   binding.
2. `SemanticEffect`: observable reads, writes, allocation, cleanup, exceptional exits, dispatch,
   synchronization, and external calls.
3. `ProtocolTransition`: finite ownership, lifetime, publication, invalidation, cleanup, or dispatch
   state transitions guarded by typed obligations.

Source-language constructs map into these planes. Rust `Drop`, C++ destruction, Zig `defer`, and
Julia cleanup are native bindings of a common cleanup protocol rather than separate graph node
ontologies. Native terms remain available for source reconstruction and proof.

## Compatibility

Legacy `FlowGraph` remains temporarily available because the C candidate, SMT, and lifting modules
consume its family-specific fields. It SHALL contain an authoritative v2 graph and serialize that
graph. C++ reports retain `graph_sha256` and `invariants` aliases while their nodes and effects come
from v2.

## Deep Emitters

C++ uses a native C++ translation unit and ABI with explicit `noexcept` and object-bound
obligations. Zig uses exported native functions over borrowed slices and vector/packed realizations.
Julia uses one concrete `Vector{UInt8}, UInt8` method specialization, generated unrolled packed and
lane realizations, and a pinned CPU-target obligation. Generated source is reconstructed before
proof, compiled or JITed natively, differentially checked, and physically measured.

ISA guards may be runtime guards or deployment guards. The graph and proof envelope SHALL state
which kind was emitted; a deployment guard may not be described as runtime feature detection.
