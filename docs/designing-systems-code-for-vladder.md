# Designing Systems Code for vLadder

## Purpose

This guide is for people and coding agents designing performance-sensitive C, C++, Rust, Zig,
Julia, GPU, and mixed systems code that may be optimized with vLadder.

It is not a request to flatten good language abstractions into C. It describes how to make the
semantic core of a system explicit enough that vLadder can:

1. identify the authoritative information and its observables;
2. close a bounded computation, state transition, lifetime, or protocol region;
3. enumerate legal implementation graphs;
4. regenerate maintainable source;
5. prove the strongest applicable equivalence claim; and
6. measure the result in the owning application.

The recommendations are based on invariant constraints of proof-gated information-flow
optimization. Frontends and grammars will broaden, but finite contracts, explicit authority,
bounded search, external-system boundaries, and physical measurement will remain necessary.

## The Design Target

The most useful architecture is not one giant "optimizable function." It has four explicit parts:

```text
owning and protocol shell
        |
        | checked bounds, versions, ownership, and dispatch facts
        v
closed semantic region
        |
        | values, state transition, exact extent, or consumer-ready tiles
        v
commit / publication boundary
        |
        v
physical workload and complete observable oracle
```

The shell may remain idiomatic and resource-safe. It can use RAII, `Vec`, allocators, errors,
exceptions, tasks, device handles, or library objects. The closed region should expose the finite
information transformation whose implementation may vary. The commit boundary makes state and
failure behavior explicit. The workload establishes whether a verified local change matters.

This separation is broadly useful even without vLadder. It improves testability, ownership review,
failure atomicity, profiling, and portability.

## Enduring Constraints

The following are architectural constraints, not temporary missing parser features.

### The semantic contract must be finite enough to encode

vLadder searches a bounded grammar under a declared contract. A region needs finite shapes,
bounded extents, explicit state projections, or a finite protocol envelope. An input size may be a
runtime value, but the rules governing traversal, failure, mutation, and outputs must be stated.

An unconstrained callback, scheduler, allocator, driver, remote service, or user-defined plugin is
not a finite semantic relation merely because it appears as one call instruction.

### Authority and observability must be explicit

Optimization is relative to observable behavior. Code should make clear:

- which state is authoritative;
- which bytes, values, errors, state transitions, ordering events, and side effects are observable;
- which data is derived and may be recomputed, retained, moved, fused, or eliminated;
- which events invalidate retained realizations; and
- which behavior is intentionally unspecified or outside the contract.

Without this distinction, eliminating a copy, retaining a cache, reordering a check, or changing a
temporary lifetime cannot be justified.

### Language semantics cannot be recovered from LLVM alone

LLVM IR is essential evidence, but it does not by itself prove source ownership, destructor order,
panic or exception behavior, object invariants, allocator contracts, callback protocols, or the
semantics of an external system. Source AST, language IR, contracts, and protocol evidence remain
part of the proof envelope.

### External authorities remain external

The internal behavior of kernels, drivers, firmware, NICs, displays, filesystems, databases,
remote services, clocks, and operating-system schedulers cannot be inferred from a local function.
vLadder can model a declared finite interaction protocol and optimize closed work on either side.
It cannot generically prove undeclared behavior inside an external authority.

### Search remains grammar-bounded

Semantic equivalence does not imply that every equivalent program can be enumerated. vLadder can
make bounded-optimality claims only inside a saturated finite region. Larger results are
`best_verified_found`. Code should expose meaningful information-flow choices, but should not be
designed around an expectation of universal algorithm invention.

### Performance remains physical and workload-specific

Proof establishes legality, not speed. Static cost models prune and prioritize. Promotion still
requires a pinned compiler, hardware target, workload, complete output oracle, paired measurements,
and application-level confirmation.

## Semantic Closure Spectrum

| Region shape | Typical vLadder disposition | Engineering implication |
|---|---|---|
| Pure bounded arithmetic over scalar values | Excellent | Keep overflow and floating-point rules explicit. |
| Borrowed contiguous input and caller-owned bounded output | Excellent | Declare extents, capacity, aliasing, alignment, and exact output length. |
| Bounded reduction, scan, recurrence, stencil, codec, or compaction | Excellent | Preserve order and failure semantics in the contract. |
| Trivial aggregate input or result | Good | Use stable field types and make all live outputs observable. |
| Direct helpers with available definitions | Good | Preserve build identity and use cross-translation-unit closure before adapting. |
| Finite object-state transition | Good with a state projection | Separate candidate state computation from commit and publication. |
| No-growth container mutation of trivial elements | Good with guards | Prove capacity before writes and prohibit reallocation on the admitted path. |
| Allocation, nontrivial destruction, or exceptions around a closed inner loop | Locally optimizable | Keep the safe owning wrapper and isolate the computation. |
| Dynamic dispatch, callback, coroutine, or task orchestration | Protocol-bound | Close concrete callees or provide a finite sequence contract; optimize neighboring regions. |
| Atomics and concurrent publication | Protocol-bound | State memory order, ownership, linearization, and retirement explicitly. |
| Syscall, driver, network, storage, or device orchestration | External boundary | Preserve calls or use a finite adapter plus physical integration evidence. |
| Undefined behavior, data races, or unspecified required behavior | Not a valid target | Repair or narrow the contract before optimization. |

`adapter_required` is a claim boundary, not a verdict on the whole source file. Closed neighboring
regions, lifetime analysis, attribution, and physical benchmarking remain useful.

## Preferred Region Interfaces

### Borrowed inputs and bounded outputs

For hot variable-output work, prefer an interface that separates storage ownership from the
transformation:

```cpp
enum class CompactStatus : std::uint8_t {
    ok = 0,
    output_too_small = 1,
    invalid_input = 2,
};

struct CompactResult {
    CompactStatus status;
    std::size_t count;
};

CompactResult compact_changed(
    std::span<std::uint32_t> output_indices,
    std::span<Value> output_values,
    std::span<const Value> current,
    std::span<const Value> baseline) noexcept;
```

This shape exposes predicate, mask, prefix/count, scatter, exact extent, and capacity-failure
semantics without making allocation part of every candidate. An owning convenience wrapper may
allocate and then call this region.

The equivalent design in another language should preserve the same semantic facts: borrowed
slices, output capacity, exact written extent, explicit failure, and no hidden ownership transfer.

### Compute then commit

For stateful work, make tentative computation and publication separate:

```text
authoritative old state + input + caller-owned scratch
    -> status + output extent + candidate state delta

candidate state delta + expected generation
    -> atomic commit or explicit rejection
```

This supports proofs of reconstruction, rollback, duplicate handling, generation selection, and
failure atomicity. It also lets vLadder search local dataflow without pretending that publication
or concurrency is ordinary arithmetic.

### Stable derived state

For repeated derivation, represent validity directly:

```text
authoritative source generation
    -> derived realization tagged with source generation

read:
    generation matches -> reuse
    generation differs -> refresh or baseline fallback
```

Do not infer a cache lifetime from observed non-mutation. Name every invalidator, authority change,
publication event, and retirement condition.

### Consumer-ready output

When an intermediate has no independent observer, expose a direct consumer or tile interface:

```text
producer -> temporary full buffer -> consumer
```

may become:

```text
producer tile -> consumer tile -> retire tile
```

or a direct write into consumer-owned storage. Keep an explicit oracle for the eliminated
intermediate until application parity is established.

## Types and Representations

### Scalars and fixed-width integers

Use fixed-width integer types at wire, storage, and packed-data boundaries. State the behavior of:

- overflow and underflow;
- signed shifts and conversions;
- division by zero and signed minimum divided by negative one;
- narrowing and saturation;
- endian conversion;
- malformed tags and lengths; and
- padding and unused bits.

Do not use a host `int`, compiler bit-field layout, or native object representation as a portable
wire contract. Decode into validated semantic values, optimize the closed transformation, then
encode explicitly.

### Enums are not inherently a problem

A closed enum with an explicit representation is a finite tag and maps naturally to bit-vector,
control-flow, and state-transition semantics. Problems arise when the enum hides unresolved
representation or validity questions.

Prefer:

- an explicit underlying/tag type where the language permits it;
- a complete list of valid values;
- an explicit policy for unknown or malformed raw tags;
- exhaustive branching with a deliberate invalid/default path;
- a separate bitmask type for independent flags;
- trivial payloads inside locally optimized tagged records; and
- decoding raw bytes before the semantic kernel.

Avoid relying on:

- implementation-selected enum width or ABI layout;
- invalid discriminants, sentinel values that are not declared variants, or unchecked integer
  transmutation;
- compiler niche layout for a cross-language, wire, or persistent representation;
- data-carrying variants with nontrivial ownership inside a local arithmetic proof unit;
- open-world subclass or plugin sets disguised as an enum; or
- default branches whose malformed-input behavior differs from the baseline.

Language examples include `enum class Kind : std::uint8_t` in C++, `#[repr(u8)]` for an appropriate
fieldless Rust enum, `enum(u8)` in Zig, and a concrete isbits `@enum` specialization in Julia. These
annotations do not prove validity by themselves. Raw input still needs checked conversion, and the
proof contract must preserve invalid-input behavior.

For C interfaces, a fixed-width integer plus named constants and a validation function is often a
clearer ABI or wire boundary than relying on implementation enum layout.

### Flags are sets, not tags

If conditions may coexist, use an explicit mask with named bits and rules for reserved bits. Do not
force independent predicates into a mutually exclusive enum. Masks expose useful grammar for
population count, selection, stable compaction, and branchless validation.

### Aggregates

Small trivial aggregates are good semantic boundaries. Keep field order, types, valid ranges, and
padding-independent equality explicit. vLadder can model register-returned and indirect `sret`
aggregates, but nontrivial copy/move/destruction and pointers whose pointees outlive the call add
ownership obligations beyond aggregate packing.

For a hot proof unit, prefer:

- trivial fields;
- no hidden self-references;
- no allocator-bearing members;
- explicit status and exact output extent;
- equality over semantic fields rather than raw structure bytes; and
- separate ownership handles from the numeric or packed payload.

### Structures of arrays and arrays of structures

Do not mechanically convert every structure to SoA. Expose the logical field projections, access
distribution, and consumers. vLadder may choose a fused pass over AoS, a projected view, an SoA
layout, or a blocked representation depending on traffic and reuse.

Stable, trivially copyable record layouts are easier to project than records containing strings,
virtual bases, allocator-bearing containers, or interior pointers. Keep those owning fields in the
shell when the hot transformation only needs a few scalar projections.

## Memory, Aliasing, and Ownership

### Bounds must dominate access

Checks should make the admitted memory footprint obvious. Prefer one dominating extent/capacity
guard to implicit assumptions distributed across helpers. A proof must connect the checked extent
to every read and write, including tails.

### Aliasing is a contract, not an optimization wish

Declare whether inputs and outputs may overlap and in which directions. Add `restrict`, noalias,
or a language-specific uniqueness assumption only when the caller establishes it. An optimization
cannot safely invent non-aliasing because the common workload happens not to overlap.

### Keep allocation outside local candidate search when practical

Allocation has success, failure, ownership, lifetime, and cleanup semantics. For load-bearing
transforms, caller-owned output and scratch usually create a cleaner search region. An outer API
may still return `std::vector`, `Vec`, an allocator-owned Zig slice, or a Julia array.

This is not a rule to avoid ownership abstractions. It is a rule to separate allocation policy
from the implementation grammar when allocation is not the optimization question.

### No-growth container mutation needs a real guard

`reserve()` somewhere earlier is not sufficient evidence. The admitted path should establish:

```text
required_output <= capacity - current_size
```

before any write, preserve container invariants, use trivial element construction where local
closure is claimed, and forbid escaped iterators or references that reallocation could invalidate.
Otherwise keep append/allocation in the owning wrapper and optimize a borrowed output region.

### Lifetimes and invalidation should be visible in types or state

For retained information, record source generation, publication state, reader ownership, final use,
and invalidators. For short-lived information, make consumer ownership and retirement explicit.
Avoid hidden process-global caches whose authority and invalidation cannot be inspected.

## Control Flow and Calls

### Structured local exits are acceptable

Ordinary early returns can be represented as tagged exits with live outputs. They become difficult
when control crosses cleanup, exception, coroutine, synchronization, or ambiguous source ranges.

Prefer a clear validation phase followed by a closed hot phase when this preserves exact error
ordering. Do not combine checks if the first reported error, side-effect order, or timing is an
observable contract.

### Avoid unbounded recursion in candidate regions

Recursion is acceptable only with a finite bound and a modeled stack/state relation. For ordinary
hot traversal, an explicit worklist or bounded iterative core is easier to search and benchmark.
Do not replace recursion merely for the tool if it changes allocation, ordering, or failure
behavior.

### Make useful helpers resolvable

Direct helpers with exact definitions can be summarized or inlined across translation units. To
support this:

- keep `compile_commands.json` or the native build manifest accurate;
- preserve concrete template or generic specializations used in production;
- avoid selecting a helper by an ambiguous source name when a mangled or specialized identity is
  available;
- keep hot helper definitions in the indexed build rather than loading them only through an
  unknown plugin; and
- make side effects and no-throw behavior accurate.

Do not manually duplicate a cross-translation-unit helper before running build closure. Multiple
weak/COMDAT definitions, unresolved function pointers, callbacks, and third-party binaries still
need a chosen identity or explicit boundary.

### Dynamic dispatch should terminate at a declared boundary

If a finite set of concrete implementations is known, use guarded dispatch and close each target
separately. If the set is open, preserve the call as a protocol boundary and optimize preparation,
postprocessing, lifetime, or batching around it.

Devirtualizing an open plugin system by assumption is not an optimization proof.

## Errors, Exceptions, Cleanup, and Undefined Behavior

### Failure behavior is part of the output

Record status values, exceptions, panics, error unions, `errno`, partial output, bytes consumed,
state mutation, cleanup, and retryability when they are observable. A candidate that produces the
same success value but changes partial failure is not equivalent.

For a local hot region, explicit status plus exact extent is often easiest to close. An idiomatic
outer wrapper may translate that status into exceptions, `Result`, error unions, or package-specific
errors.

### Keep cleanup correct, not invisible

RAII, `Drop`, `defer`, finalizers, and destructors are valuable safety mechanisms. Do not remove
them to satisfy a local frontend. Isolate the load-bearing pure or bounded stateful computation
inside the owning scope and prove cleanup/publication separately.

When exceptional exits cross object construction or mutation, provide a finite cleanup protocol or
retain the original call boundary. `noexcept` should reflect reality; it is not a proof hint to add
without establishing every callee path.

### Undefined behavior is not an optimization degree of freedom

vLadder does not repair undefined behavior as part of equivalence. Eliminate data races, invalid
pointer arithmetic, out-of-range shifts, signed overflow where forbidden, lifetime violations, and
invalid discriminants before optimization. State deployment preconditions only when they are real
and checked or guaranteed by the owning system.

## Numerical Semantics

Declare one of the following before search:

- bitwise exact;
- exact integer/bit-vector semantics;
- IEEE operation-order equivalent;
- deterministic tolerance-bounded;
- distributionally bounded; or
- explicitly approximate.

Also declare NaN, infinity, signed zero, subnormal, rounding, contraction, reassociation,
determinism, and overflow policy. Do not enable `fast-math`, fused operations, fixed-point
replacement, or approximate transcendentals and retroactively call the result equivalent.

For tolerance modes, define the complete quality observable and deterministic tie-breaking.
Decoded quality alone may not cover encoded-byte identity, reproducibility, or downstream branch
behavior.

## Stateful and Incremental Systems

Stateful optimization works best when code identifies:

- authoritative old state;
- input event and sequence/generation identity;
- candidate next state;
- emitted output or delta;
- commit guard;
- rollback behavior;
- duplicate and reorder behavior;
- invalidation and retirement; and
- reconstruction invariant.

Prefer immutable snapshots, explicit deltas, generation IDs, and single publication points over
many hidden mutations interleaved with external calls. If mutation must be incremental, expose the
finite transition and every intermediate observable.

For dependency invalidation, keep identity, dependency edges, dirty roots, closure order,
deduplication, and revision commit explicit. This belongs primarily to lifetime/protocol grammar,
while local set, sort, compaction, and traversal helpers remain compiled-code regions.

## Concurrency

The easiest high-performance contract is single-thread ownership of mutable state with explicit
handoff. When concurrency is required, state:

- participating threads or agents;
- memory locations and ownership;
- atomic width and memory order;
- linearization or publication point;
- allowed reorderings;
- progress expectations;
- cancellation and failure behavior;
- reader retirement; and
- reclamation mechanism.

Keep local data preparation separate from atomic publication when possible. A local proof can then
cover preparation, while a finite protocol proof covers publication. Arbitrary scheduler behavior,
general lock-free reclamation, and undeclared races cannot be reduced to an expression grammar.

Do not weaken atomics or barriers based only on a benchmark. A faster candidate must first satisfy
the memory-model contract.

## External I/O and Protocols

For files, sockets, storage, drivers, and remote services, make partial outcomes explicit:

- short read/write;
- interruption and retry;
- timeout;
- ordering;
- duplicate delivery;
- backpressure;
- resource acquisition and release;
- error code and state after failure; and
- ownership transfer.

Optimization can target packing, validation, batching, retained serialization, queue preparation,
and state transitions. The external call itself should remain boundary-preserving unless a finite
replacement protocol and authoritative oracle exist.

Opaque calls do not need to block the whole workflow. Treat them as zero-dimensional protocol
constraints: they reduce legal transformations but do not add implementation candidates.

## GPU and Heterogeneous Code

Separate device computation from host orchestration.

Device kernels are most tractable when they have:

- explicit dispatch dimensions and index mapping;
- bounded buffers, formats, descriptors, and address spaces;
- declared alias and synchronization rules;
- deterministic output or a declared numerical contract;
- no hidden device allocation in the hot kernel;
- complete output hashing or comparison; and
- clean device timestamps for physical ranking.

Host orchestration should expose resource generations, queue ownership, barriers, semaphore or
timeline values, acquire/release, and failure paths. vLadder can prove declared finite protocol
relations, but it cannot infer proprietary driver scheduling, firmware, display scanout, or DMA
behavior from SPIR-V, PTX, CUDA, or Vulkan host code.

Do not treat SPIR-V validation, PTX compilation, static occupancy, or a simulated runner as output
equivalence or a physical speedup.

## Language-Specific Surfaces Without Language-Specific Ontologies

All frontends should map into common values, control, state, memory, materialization, transfer,
ownership, lifetime, and protocol concepts. Language-specific features remain bindings and proof
obligations unless they introduce a genuinely new semantic concept.

### C

Prefer explicit pointer/extent pairs, fixed-width boundary types, caller-owned output, direct
helpers, and a declared alias contract. Keep macro-expanded build identity and compilation flags.
Treat pointer provenance, effective type, alignment, overflow, `volatile`, and `errno` as semantic
facts, not compiler trivia.

### C++

Use `std::span` or equivalent borrowed views for closed hot regions, trivial records for projected
data, explicit enum representations, concrete template specializations, and accurate `noexcept`.
Keep allocation, nontrivial ownership, virtual dispatch, exception translation, and RAII in an
owning wrapper unless those protocols are themselves the bounded optimization target.

Idiomatic iterators are acceptable, but a contiguous span/index view often exposes bounds,
projection, aliasing, and output extent more directly for a load-bearing proof unit.

### Rust

Use safe monomorphic functions over borrowed slices for closed computation. Preserve borrow,
panic, overflow, unsafe preconditions, and `Drop` behavior. Keep owning collection growth,
async/task orchestration, FFI, and custom destruction at explicit boundaries unless a finite state
protocol is supplied. Do not introduce `unsafe` merely to make generated code resemble C.

### Zig

Use concrete compile-time specializations and borrowed slices with explicit safety mode. Keep
allocator ownership, error unions, `defer`/`errdefer`, volatile/atomic access, assembly, and FFI as
declared obligations or boundaries. A generated total inner function can remain behind an
idiomatic error-returning wrapper.

### Julia

Use concrete, type-stable method specializations and function barriers around dynamic code. For a
closed hot region, make allocation behavior, element types, shapes, globals, world identity, and
exceptions explicit. Warm and benchmark steady-state execution separately from compilation.
One method specialization does not prove a generic function in every future world.

## Patterns That Commonly Hide Useful Information Flow

| Pattern | Why it is difficult | Better boundary |
|---|---|---|
| Return a newly allocated container from every transform | Allocation and computation are entangled | Owning wrapper plus borrowed output kernel |
| Push into a vector with implicit possible growth | Capacity, relocation, cleanup, and iterator validity are hidden | Dominating no-growth guard or caller-owned span |
| Use a callback for every element | Target identity, ordering, exceptions, and effects may be open | Close a finite callback target or isolate map/filter dataflow |
| Mutate authoritative state while constructing output | Partial failure and publication are interleaved | Compute candidate delta, then commit once |
| Rebuild derived data on every consumer | Semantic lifetime and invalidators are hidden | Versioned retained realization with fallback |
| Keep duplicate CPU/GPU copies without authority metadata | Placement and freshness are ambiguous | One authority plus versioned derived placement |
| Serialize a whole logical body per fragment | Invariant body lifetime is too short | Record-lifetime body plus fragment envelope |
| Encode tags through compiler object layout | ABI, padding, and invalid values are implicit | Validated fixed-width codec |
| Rely on global mutable configuration in a hot helper | Input identity and invalidation are hidden | Explicit immutable configuration/version input |
| Mix timing, logging, I/O, and arithmetic in one loop | Observables prevent reordering and fusion | Instrument at region boundaries |
| Require byte equality of padded structs | Padding may be indeterminate and nonsemantic | Compare named fields or canonical serialization |

## Do Not Contort the Application for the Tool

The following changes are usually wrong:

- replacing RAII, safe ownership, or `Drop` with raw lifetime management;
- adding `restrict`, unchecked indexing, `unsafe`, or `@inbounds` without a proved precondition;
- turning every abstraction into one monolithic C ABI;
- flattening errors or exceptions when their order and cleanup are observable;
- adding caches without complete invalidation and memory budgets;
- changing data layout across an API without adapters or transforming every consumer;
- removing a protocol call because its return value appears unused;
- adding manual SIMD before measuring whether representation, lifetime, or traffic dominates; or
- designing only for the current grammar version.

Instead, add a narrow semantic seam: a borrowed view, finite state projection, checked dispatch
guard, caller-owned buffer, exact helper summary, or protocol adapter. Keep the application-facing
API idiomatic.

## Attribution and Benchmarkability

Optimization-friendly code should also be measurable. Provide:

- a stable build and exact source/compiler identity;
- a way to select baseline and candidate in one executable;
- deterministic fixtures or recorded workload traces;
- complete output and state reset oracles;
- warm and cold regimes where relevant;
- representative and adversarial input distributions;
- attribution for cycles, bytes, cache traffic, stalls, branches, allocation, and synchronization;
- an end-to-end boundary that includes moved rather than merely removed cost; and
- explicit overlap relationships among regional benchmarks.

Do not sum overlapping local speedups. Require an interaction benchmark for composed changes.
Distinguish a newly discovered optimization from revalidation of an already retained one.

## Agent Workflow

An attending agent should follow this decision order:

1. Freeze source, build, compiler, target, workload, and semantic contract.
2. Attribute the load-bearing region before proposing a grammar family.
3. Identify authority, observables, lifetimes, invalidators, ownership, and external actors.
4. Capture the exact source region and read independent closure capabilities.
5. Run whole-build or cross-translation-unit closure for definition-visible helpers.
6. Choose the correct level: compiled region, bounded dataflow, state protocol, lifetime,
   operator/pipeline, or GPU workflow.
7. Isolate closed subregions without weakening the owning contract.
8. Generate candidates only from an attributed grammar with satisfied guards.
9. Prove structural, Z3, LLVM, protocol, and differential obligations at their actual scopes.
10. Benchmark baseline and candidate in the same executable with complete observables.
11. Realize the exact proved candidate in maintainable project source.
12. Run project tests and the end-to-end workload before promotion.

Stop at the first missing evidence state. Report whether the outcome is:

- selection only;
- meaningful semantic capture;
- candidate generated;
- candidate proved;
- physically benchmarked;
- application integrated; or
- production promoted.

Do not call successful command execution an optimization.

## Design Review Checklist

### Information and observables

- Is authoritative state named?
- Are all outputs, errors, side effects, ordering events, and state transitions identified?
- Are derived values distinguished from authority?
- Are invalid and malformed inputs specified?

### Shapes and memory

- Are lengths, strides, capacities, alignment, and tails explicit?
- Are alias and overlap rules stated?
- Can allocation be separated from the closed transformation?
- Is output extent explicit and checked before writes?

### Types and arithmetic

- Are boundary integers fixed-width?
- Do enums have explicit representation and invalid-tag behavior?
- Are aggregates trivial or are copy/move/destruction obligations modeled?
- Are overflow, shifts, floating point, NaN, and determinism declared?

### Control and calls

- Are loops and recursion bounded?
- Do early exits cross cleanup, synchronization, or exceptions?
- Are direct helper definitions available in the indexed build?
- Are dynamic or external callees preserved as explicit boundaries?

### State and lifetime

- Is old state separated from candidate next state and commit?
- Are generations, invalidators, fallback, and retirement explicit?
- Can stable and mutable projections be split?
- Is retained memory bounded and attributed?

### Concurrency and protocols

- Is mutable state single-owner where practical?
- Are memory order and publication points explicit?
- Are partial I/O, retries, cancellation, and failure state specified?
- Is external-system behavior distinguished from local compiled behavior?

### Evidence and promotion

- Is there a complete differential oracle?
- Is the physical benchmark representative and paired?
- Are regional overlaps modeled?
- Does the application workload include moved setup, invalidation, and retention costs?
- Can the generated source be traced exactly to the proved candidate?

## What Future vLadder Versions May Improve

Future releases may close more aggregate ABIs, container idioms, enum spellings, helper relations,
state machines, GPU operations, language IR patterns, and source regeneration routes. They may
automate more adapter construction and larger graph search.

Those improvements will not remove the need for:

- explicit semantic authority and observables;
- finite, inspectable contracts;
- bounded implementation grammars;
- language-level ownership and failure evidence;
- external protocol boundaries;
- exact build and specialization identity;
- proof scopes that match their claims;
- physical measurement on the target workload; and
- honest bounded-optimality language.

Design for those invariants. Code that makes information identity, lifetime, placement, mutation,
and observation explicit will remain tractable as vLadder grows, even when the exact frontend or
grammar used to optimize it changes.
