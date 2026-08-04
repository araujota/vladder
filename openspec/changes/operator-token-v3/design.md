# Design: Token-Generation Operators V3

The first vertical slice is residual + RMSNorm + symmetric int8 quantization.
It exercises reduction, a private intermediate, three input streams, two
outputs, numerical tolerance, and eliminated traffic. The comparator set
includes staged C, hand-fused C, Clang variants, and the pinned llama.cpp
RMSNorm+multiply kernel where contracts overlap.

RoPE, online attention reduction, quantized epilogues, and sampling are separate
OperatorGraphs sharing tensor metadata. End-to-end model tests are optional
until a model artifact and license-compatible checksum are present; absence must
not be silently replaced by a synthetic claim.
