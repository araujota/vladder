# Design: SKSF Production Projection and Pipeline Integration V6

Production integration uses the pinned model, llama.cpp commit, CPU backend, and active
native-repack path. Runtime plans dispatch on phase, token tile, sequence count, context,
ISA, alignment, and KV occupancy. Every dispatch arm has proof, benchmark, and fallback
coverage. KV grammar is admitted only after a target attribution study makes it material.
