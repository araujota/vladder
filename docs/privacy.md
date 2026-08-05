# Privacy And Network Policy

## Default

vLadder is local-only by default. Source files, compilation databases, LLVM IR, assembly, traces,
proofs, benchmark samples, model files, and generated patches remain on the machine in the output
paths selected by the user. The Python package contains no telemetry SDK and optimization commands
make no background network requests.

Network access occurs only in explicit administrative operations:

- installation may download system packages, language toolchains, Alive2, or a release artifact;
- publishing commands operated by maintainers contact release services;
- `vladder review submit` sends one schema-validated agent-review record only after
  `--confirm-upload` and record-level consent;
- `vladder training submit` sends one schema-validated, source-free derived-feature bundle only
  after the same two consent gates.

The release endpoints are built into the package so contributors do not need a shared credential.
Public submissions are rate-limited, idempotent, private by default, and enter moderation. Endpoint
environment variables may override the release service; a trusted contribution token is optional.
`--validate-only` exercises remote schema acceptance without storing the record.

Review records cannot contain source or raw artifact attachments. Training bundles contain only
bounded numeric/categorical features, content hashes, grammar identifiers, proof dispositions, and
measurement labels. Their schema rejects source, raw artifacts, prompts, and personal data. The
CLI never uploads a local prior store, compilation unit, proof bundle, or arbitrary file.

## Threat Model

Do not place secrets in manifests, contribution JSON, benchmark output, or public issue reports.
Review every generated record before changing `privacy.submission_consent` to true. Maintainers
may supply a trusted token through `VLADDER_CONTRIBUTION_TOKEN`; ordinary users do not need one.

External compilers, profilers, project test commands, and benchmark runners execute with the
current user's permissions. vLadder is not a sandbox. Use a container or isolated machine for
untrusted source and untrusted runner commands.
