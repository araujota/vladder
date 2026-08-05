## Architecture

All languages continue to lower into SemanticFlowGraph v2. Language adapters own only project
loading, concrete method/symbol binding, ABI closure, compiler provenance, and native source
emission. Semantic operations, effects, protocols, graph nodes, and grammar rules remain shared.

The corrected evidence chain is:

1. bind an exact source/module/method and compilation world;
2. capture typed/native compiler IR without invoking an arbitrary production function;
3. recognize semantics from structured or boundary-aware evidence;
4. derive candidates from one shared grammar;
5. emit and compile native source;
6. bind source, graph, and compiler artifacts;
7. prove the shared bounded obligation and run native differential tests;
8. fingerprint a resolved hot symbol or method body;
9. physically rank every unique resolved realization;
10. reserve bounded optimality for complete, non-empty physical coverage.

## Physical Identity

The ranker resolves symbols from object or executable symbol tables and uses symbol-scoped
disassembly where available. Textual assembly and LLVM IR are explicit fallbacks. An empty body is
`identity_unresolved`, not a valid digest. Unresolved candidates are measured independently and
prevent an exhaustive classification.

## Zig Capture

The generated capture root imports the target as a named module using Zig's module command-line
model. The target remains at its original path, preserving relative imports and file-namespace
semantics. Wrapper generation is signature-driven. Unsupported signatures may still receive
module/compiler capture, but cannot receive a candidate or local proof claim.

## Julia Capture

Package sources are loaded through the declared project and module. `which`, `code_typed`,
`code_llvm`, and `code_native` bind an exact tuple signature without executing the method.
Allocation/differential evidence is a separate optional phase requiring valid generated samples.
Standalone source inclusion remains an explicit fallback, not the default package path.

## Shared Bounded Dataflow

The five existing families and seventeen terminals gain C, Zig, and Julia emitters. The native
surface preserves exact extent, stable order, capacity behavior, packed bytes, state publication,
and block tie-breaking. Language-specific ISA realizations may be guarded or scalarized when the
frontend cannot express the instruction directly, but coverage reports distinguish semantic
emission from physically distinct lowering.

## Research Basis

LLVM documents `llvm-nm` for defined symbol discovery and `llvm-objdump
--disassemble-symbols` for symbol-scoped machine-code inspection. Zig defines every source file as
an implicit namespace/module, so relocating a source file changes import resolution. Julia's
InteractiveUtils exposes method-specialized typed, LLVM, and native code inspection, while its code
loading model binds packages through an active project. These interfaces are used as provenance
boundaries rather than approximated with source copies or arbitrary calls.

## Acceptance Corpus

Fixtures cover every emitted terminal. Pinned upstream samples cover zlib, xxHash, fmt,
fast_float, Zig standard-library/known-folders regions, Parsers.jl, and StaticArrays.jl. Upstream
trees are hashed before and after. Unsupported semantics are successful scoped dispositions, not
candidate-generation successes.
