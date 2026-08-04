## Decisions

### Build once and publish identical artifacts

The tag workflow builds one audited wheel and sdist. GitHub and PyPI consume those artifacts. The
Homebrew formula references the exact GitHub release sdist and pins every resource hash.

### Use credentialless Python publication

PyPI and TestPyPI use GitHub OIDC trusted publishing with protected environments. No package token
is stored in workflow YAML or repository secrets.

### Keep architectural claims bounded

Release validation proves that the lifetime graph, grammar, Z3 obligations, stateful replay, and
agent contract execute on the isolated corpus. It does not claim an implemented NeuralFusion
rewrite or application speedup. Lifetime plans remain repository-agent adapters.

### Keep external tool boundaries explicit

PyPI installs Python dependencies. The Linux installer provisions LLVM, llvm-mca, Z3, Alive2, and
perf where supported. Homebrew installs Python, LLVM, and Z3; `vladder doctor` remains authoritative
for strict host readiness.
