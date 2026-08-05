# RC12 Cross-Language Capture Evaluation

Date: 2026-08-05

This evaluation tests semantic capture and candidate generation without modifying any upstream
source tree. It is an acceptance study for evidence correctness and frontend behavior, not a claim
that the selected upstream functions are representative performance opportunities.

## Pinned corpus

| Language | Project | Revision | Region |
|---|---|---|---|
| C | zlib | `e3dc0a85b7032e98380dec011bc8f2c2ee0d8fca` | `adler32_z`, `crc32_z` |
| C | xxHash | `c0b5ea995d66691734b1a79ad89e73a0d2fd5a53` | `XXH64` |
| C++ | fmt | `60ccad511fd680cb91d8b60a315759f71c67bef9` | `convert_c_format_args` |
| C++ | fast_float | `f6df0f29174054bb1ed06a9945416c8946a01292` | `from_chars<int, char>` |
| Zig | known-folders | `6da0d0c41b78b9ed2d34fa364fcb81b5ebece6c4` | `getPath` |
| Julia | Parsers.jl | `24a05a9979e9d7ba0b4665803b73a81cd0316ea8` | `parse(::Type{Int64}, ::Vector{UInt8})` |
| Julia | StaticArrays.jl | `f02280c5c1f05c56a52fbe45168e2961416c3f89` | `_norm_p0(::SVector{4,Float64})` |
| Zig | Zig 0.16 standard library | installed toolchain | `std.mem.countScalar(u8, ...)` |

The before/after `git status --porcelain` snapshots are byte-identical for every cloned project.

## Results

| Region | Compiler capture | Shared semantic graph | Candidates | Disposition |
|---|---:|---:|---:|---|
| zlib `adler32_z` | no | no | 0 | canonical C ABI adapter required |
| zlib `crc32_z` | no | no | 0 | canonical C ABI adapter required |
| xxHash `XXH64` | no | no | 0 | macro/header extraction adapter required |
| fmt `convert_c_format_args` | yes | local effects/ABI | 0 | C++ proof unit only; external call and multi-exit source lowerer required |
| fast_float `from_chars<int,char>` | yes | local effects/ABI | 0 | aggregate-result source lowerer required |
| Zig `std.mem.countScalar(u8,...)` | yes | yes | 4 | all proved and differentially valid; all physically rejected |
| Zig known-folders `getPath` | yes | no | 0 | allocation, `defer`, error/ownership, and operation adapters required |
| Parsers.jl integer parse | yes | no | 0 | operation, bounds-failure, exception, and result-shape adapters required |
| StaticArrays.jl fixed-vector norm | yes | no | 0 | fixed aggregate and floating-point operation contract required |

`std.mem.countScalar` is the only upstream region in the current executable byte-reduction
grammar. Project-native capture preserves its standard-library module scope and specializes the
`comptime` element type. The four generated schedules pass the bounded Z3 schedule theorem,
canonical LLVM refinement, and native differential oracle. The physical screen rejects all four:
the installed standard library lowers to a substantially stronger vector implementation. The
screen used only two process pairs and therefore supports rejection, not publication-grade effect
sizes.

## Fixture coverage

The shared bounded-dataflow grammar has five families and seventeen terminals. RC12 emits all
terminals as native C, C++, Zig, and Julia source. C, Zig, and Julia add 51 native bindings; every
binding compiles and passes its language-native differential harness. Non-scalar ISA-named
terminals currently use an explicitly reported semantic scalar fallback in languages where no
distinct intrinsic lowerer is implemented. This is semantic grammar coverage, not a claim of 68
physically distinct machine realizations.

The deep byte-reduction grammar resolves non-empty hot identities for all six Zig and Julia
terminals. Tiny physical coverage runs close as `bounded_optimal_local`; their timing samples are
deliberately too small for performance conclusions.

## Remaining general gaps

1. The legacy C automatic frontend still assumes the original float-transform ABI. Shared native
   C emission exists, but arbitrary C source recognition and ABI normalization do not.
2. C++ compiler capture is broader than executable source regeneration. Aggregate returns,
   escaping control flow, helper summaries, and ownership protocols remain named adapters.
3. Zig project capture is now native, but allocator/error/defer semantics are not part of the
   bounded reduction grammar.
4. Julia exact method reflection is now native, but general typed-IR-to-shared-operation
   recognition is not. Dynamic effects, exceptions, GC ownership, and aggregate values remain
   outside automatic proof closure.
5. Native bounded-dataflow fallback emitters preserve semantics but do not necessarily create a
   physically distinct implementation. Physical identity remains a separate acceptance gate.

These are scoped grammar and source-realization limits. They do not block attribution, local graph
capture, proof-unit isolation, or adding a bounded shared operation with native emitters.
