# Design: SKSF Layered Verification V6

Each layer produces a content-addressed artifact and explicit coverage boundary. Alive2
validates supported LLVM transformations; SMT/CEGIS handles bounded bit-vectors and
memory footprints; differential tests cover complete kernels and sequences; model tests
cover logits, tokens, dispatch, and KV state. Unsupported is not equivalent to proved.
