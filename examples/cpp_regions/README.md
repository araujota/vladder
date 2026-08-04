# Bounded C++ Region Validation Workspace

This corpus exercises the `bounded-cpp-regions-v4` frontend independently of application code.
Tests generate `compile_commands.json` with absolute paths so the fixtures remain relocatable.

Supported fixtures isolate into canonical C kernels. Adapter fixtures must fail closed with the
documented C++ semantic boundary.

The v4 fixtures additionally cover byte spans, aggregate results, compiler-inferred no-unwind
behavior, structured borrowed views, local loops inside owning wrappers, and external protocols.
They verify whole-function identity proof units, nested lambda capsules, guarded loop-schedule
candidates, escaping-control rejection, categorical protocol scopes, and fail-closed benchmark
adapters. Generated source is never applied by the fixture workflow.
