# Bounded Region Closure v6

## Result

The five reported C/C++ gaps do not have one answer.

| Gap | Closure | Executable scope | Remaining boundary |
|---|---|---|---|
| First-order ABI | Scalar/POD results and scalar or borrowed pointer/extent inputs | Existing grammar or IR proof unit | Variadics, callbacks, opaque ownership and unbounded declarators |
| Aggregate result | Ordered source fields bound to register projections or `sret` | Local LLVM transformations | Nontrivial copy/destruction, pointer-target lifetime, class invariants |
| Multi-exit | Ordinary returns represented by exit tag plus live-outs | Whole-function schedule candidates | `goto`, coroutine, unwind and cleanup-crossing exits |
| Helper summary | Inlined helper or exact definition-visible call-preserving relation | Rewrites preserving the call boundary | Cross-call rewrites need inlining or a functional proof; indirect/external calls remain protocols |
| Ownership | Dominating no-growth guard plus trivial append projection | Bounded local container region | Reallocation, allocator changes, nontrivial lifetime and escaped iterators |

This is information-flow closure, not broad syntactic acceptance. `AggregatePack`, `ExitMerge`,
`HelperSummary`, `OwnershipGuard`, and `Append` expose values that were previously hidden behind the
source ABI or library surface. Existing loop, dataflow, lifetime, LLVM, proof, and benchmark layers
can operate after that boundary is explicit.

## Physical Basis

LLVM makes aggregate extraction/insertion and CFG control explicit in its IR, while ABI attributes
describe indirect result storage. The Itanium C++ ABI returns trivial class values through the base
C ABI but uses indirect handling for nontrivial call types. C++ vector insertion can reallocate and
invalidate references, so a capacity observation alone is insufficient; vLadder requires a
dominating spare-capacity proof and trivial element lifetime.

Primary references:

- <https://llvm.org/docs/LangRef.html>
- <https://itanium-cxx-abi.github.io/cxx-abi/abi.html>
- <https://eel.is/c++draft/vector.modifiers>
- <https://clang.llvm.org/docs/LibASTMatchers.html>

## Claims

The closure proof establishes representation identities and finite guards. It does not establish
the semantics of a newly generated candidate, an owning wrapper, an allocator, an exception
protocol, or an external API. Reports retain those as explicit unresolved boundaries.

## Pinned Upstream Recheck

Read-only reinspection used the already pinned zlib, fast_float, and fmt revisions and their
existing compilation databases. All three worktrees remained clean.

| Region | Previous dominant gap | v6 result | Still missing |
|---|---|---|---|
| zlib `adler32_z` | canonical ABI rejected | first-order typedef/pointer ABI closed | Adler grammar and executable lowering |
| zlib `crc32_z` | canonical ABI rejected | first-order typedef/pointer ABI closed | CRC grammar and executable lowering |
| fast_float integer `from_chars` | aggregate result lowerer | aggregate fields and inlined helper relation closed at compiled IR | deterministic source grammar for the parser |
| fmt `convert_c_format_args` | helper and escaping return | inlined helper relation plus tagged whole-function CFG; source schedule mode available | application benchmark and candidate-specific physical proof |

Artifacts are under `/tmp/vladder-region-closure-v6-upstream-20260805`. These are semantic capture
results, not performance wins.
