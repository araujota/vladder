# Design: Q4_K Baseline Reconstruction and Parity V7

The baseline generator extracts the pinned function body, renames it, and compiles it as
an independent translation unit with equivalent ISA and optimization flags. The harness
compares native and generated symbols bitwise on adversarial, random, and complete FFN
dimensions. Ranking uses randomized independent process medians and bootstrap intervals.

Model verification compiles the regenerated symbol as an opt-in preload library. Dynamic
linker binding evidence is required so an unchanged model output cannot falsely pass when
the override was not used.
