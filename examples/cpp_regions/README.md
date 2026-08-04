# Bounded C++ Region Validation Workspace

This corpus exercises the `bounded-cpp-regions-v2` frontend independently of application code.
Tests generate `compile_commands.json` with absolute paths so the fixtures remain relocatable.

Supported fixtures isolate into canonical C kernels. Adapter fixtures must fail closed with the
documented C++ semantic boundary.
