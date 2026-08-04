# Design: Operator Verification V3

Verification is layered and fail-closed. Structural checks run first. Exact
integer/bitvector and bounded state transitions use Z3/CBMC. LLVM refinements use
Alive2 only where tractable. Floating point uses bitwise checks for exact rules
and high-precision/adversarial error envelopes for declared tolerance modes.
Sequence tests compare every output, final state, invariants, and reproducibility.

The SPSC model permits one producer and one consumer, fixed capacity, and
acquire/release publication. Alternative memory orders need a litmus proof and
stress evidence; neither alone establishes general lock-free correctness.
