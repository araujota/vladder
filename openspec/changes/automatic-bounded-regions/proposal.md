## Why

The registry-driven engine can lower every vocabulary rule into a plan, but source-capable work
still depends on callers selecting specialized commands and shapes. vLadder needs one automatic
path that extracts a bounded region, classifies support, regenerates transformed source, executes
the complete proof chain, and reports precise adapter requirements for unsupported code.

## What Changes

- Define a finite automatic region support matrix.
- Add structural extraction and exact ordered-unroll regeneration for supported single-loop regions.
- Add typed adapter requirements for unsupported ABI, loop, side-effect, concurrency, and graph shapes.
- Integrate generated candidates into strict Z3, memory, Alive2, differential, benchmark, and patch promotion.
- Add public API and CLI surfaces for support inspection and automatic optimization.
- Validate against an isolated fixture workspace rather than an actively edited application.

## Impact

The automatic path supports bounded canonical C array regions and fails closed outside that set.
Existing specialist operator, pipeline, and kernel workflows remain available for richer shapes.
