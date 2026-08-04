# Design: Projection Verification V5

Exact layouts are permutations of opaque fixed-size blocks. Verification proves a
bijection over block identities, checks byte-for-byte inverse reconstruction, records
source/transformed/inverse hashes, and excludes padding from the domain. Projection
plans compose this proof with shape, alias, quantization, tile, guard, and numerical
obligations. Model acceptance still requires deterministic generated-token evidence.
