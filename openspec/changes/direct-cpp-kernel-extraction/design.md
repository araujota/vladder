## Context

The existing `bounded-regions-v1` path parses C with regular expressions and assumes an
unmangled `void (float *, const float *, size_t)` function. C++ requires a semantic frontend:
compile flags affect templates and overload resolution, functions are mangled, and local-looking
code may carry destructor, exception, ownership, or concurrency behavior.

## Decisions

### 1. Use the production compile command

The frontend resolves exactly one compilation-database entry, prefers its structured `arguments`
array, preserves semantic flags, and fails closed on ambiguous entries. Diagnostic and output
flags are removed before invoking the pinned Clang frontend.

### 2. Select through the Clang AST

Function selection uses Clang's semantic AST and records the concrete mangled symbol. Overloaded
or multiply instantiated targets require an explicit symbol selector. Source extraction never
falls back to first textual-name match.

### 3. Isolate only explicit bounded classes

The first C++ support matrix accepts:

- a `noexcept` free/static function or state-independent method with the canonical pointer ABI;
- a `noexcept` free/static function or state-independent method taking writable and read-only
  dynamic `std::span<float>` views and deriving `n` from the source span;
- a `noexcept` borrowed `std::vector<float>` view with stable storage and no metadata mutation;
- the same shape from a concrete Clang-emitted template instantiation.

The region must otherwise satisfy the existing single-loop exact support matrix. Use of `this`,
allocation, destruction protocols, exceptions, virtual or indirect calls, atomics, volatile
state, inline assembly, coroutines, or unmodeled calls requires a typed adapter.

### 4. Split the proof claim

The isolated C kernel is eligible for complete local refinement proof. The C++ adapter receives a
separate Z3 proof that its declared extent preconditions make every generated pointer access
in-bounds. AST legality and successful compilation establish the syntactic bridge. This is
classified as `kernel_proved_adapter_bounded`, never whole-method Alive2 equivalence.

### 5. Regenerate C++ from the chosen information-flow realization

The frontend emits a canonical C kernel, a C++ translation unit with a private helper and
replacement wrapper, a replacement body, and provenance linking source AST, production LLVM IR,
kernel source, adapter contract, and generated realization.

## Non-Goals

- Interprocedural Alive2 proof.
- General exception, destructor, allocator, ownership, callback, Vulkan, OpenUSD, or concurrent
  queue equivalence.
- Automatic semantic modeling of arbitrary standard-library containers.
- Optimization of code that cannot be isolated without changing an owning protocol.
