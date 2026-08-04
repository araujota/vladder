# Design: Q4_K Active Path Capture V7

Capture is disabled by default and emits one structured record at the existing dispatch
boundary when `SILICONTUNE_CAPTURE_Q4K_PATH=1`. The extractor records both GEMM prompt
and GEMV decode records but gates V7 on the decode symbol. Pre/post hardware manifests
must match. The source remains the authoritative path description; symbol and assembly
metadata provide independent provenance.
