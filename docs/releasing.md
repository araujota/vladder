# Releasing vLadder

The release decision is target-specific. A local development pass does not imply that GitHub,
PyPI, Homebrew, or the complete formal release is ready.

## Canonical Check

From a source checkout with development dependencies and `@fission-ai/openspec@1.7.0` installed:

```bash
vladder release check --execute --require-target release_candidate \
  --out build/release-readiness.json
```

Immediately before tagging:

```bash
vladder release check --execute --online --require-target formal_release \
  --out build/release-readiness.json
```

When only account-side state changed, reuse a matching full local report instead of repeating the
five-minute functional suite:

```bash
vladder release check --online --reuse-local-report build/release-readiness.json \
  --require-target formal_release --out build/release-readiness.json
```

Reuse fails if the root, version, report schema, or prior `--execute` evidence does not match.

The JSON report records every check as `pass`, `fail`, `not_run`, `setup_required`, `unavailable`,
or `warning`, lists which release targets it blocks, and supplies one remediation. Do not publish
based on a subset of green commands.

## One-Time GitHub Setup

1. Keep `araujota/vladder` public with `main` as the default branch.
2. Protect `main` and require the `CI` workflow before merge.
3. Create protected GitHub environments named `testpypi`, `pypi`, and `homebrew`. Require
   maintainer approval for publication environments.
4. Create the public tap repository `araujota/homebrew-tap` with `brew tap-new araujota/tap`.
5. Set repository variable `HOMEBREW_TAP_REPOSITORY=araujota/homebrew-tap`.
6. Add environment secret `HOMEBREW_TAP_TOKEN` containing a fine-grained token with contents write
   access only to `araujota/homebrew-tap`.
7. Set `tap_configured = true` in `release/channels.toml` only after the tap is usable.

## PyPI And TestPyPI Setup

The package name is `vladder`. It must be configured independently on PyPI and TestPyPI.

For an unclaimed project, create a pending Trusted Publisher with:

| Field | PyPI | TestPyPI |
|---|---|---|
| Owner | `araujota` | `araujota` |
| Repository | `vladder` | `vladder` |
| Workflow | `release.yml` | `test-publish.yml` |
| Environment | `pypi` | `testpypi` |
| Project | `vladder` | `vladder` |

For an existing project, add the same publisher from its publishing settings. Trusted Publishing
uses GitHub OIDC and `id-token: write`; do not add a PyPI username, password, or API token. The
official procedures are [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
and [creating a project through OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

The GitHub environments enforce the other half of this trust relationship:

* `pypi` requires maintainer approval and accepts only tags matching `v*`.
* `testpypi` requires maintainer approval and accepts only the `main` branch.

The environment name is part of the OIDC identity and must exactly match the corresponding Trusted
Publisher form. No environment secret is required or expected.

After both publishers exist, set their `trusted_publisher_configured` values to `true` in
`release/channels.toml`. This is a reviewed local attestation because PyPI does not expose pending
publisher configuration through its public project JSON API.

## Release Procedure

1. Update `CHANGELOG.md`; synchronize the version in `pyproject.toml`, `vladder/__init__.py`, and
   release assertions.
2. Run the release-candidate check and inspect every non-pass result.
3. Trigger the `TestPyPI` workflow. Install that exact prerelease in a clean environment and run:

   ```bash
   python3 -m pip install --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ --pre 'vladder==<VERSION>'
   vladder --version
   vladder schema list
   vladder skill validate
   ```

4. Commit all reviewed release changes so the formal online check sees a clean tree.
5. Run the formal release check.
6. Create and push an annotated tag matching the package version:

   ```bash
   git tag -a v<VERSION> -m "vLadder <VERSION>"
   git push origin main v<VERSION>
   ```

The tag workflow reruns the formal check, builds one wheel and one sdist, verifies the generated
formula on macOS, creates the GitHub release, publishes the same distributions to PyPI using OIDC,
and updates the configured tap. It fails before publication if any required channel is not ready.

## Homebrew Verification

The formula contains exact hashes for vLadder and every Python resource. The release workflow runs
a source build and formula test on macOS before publication. The tap update additionally runs the
official audit against published URLs. Homebrew maintainers recommend `brew audit`, source install,
and `brew test`; see the [Formula Cookbook](https://docs.brew.sh/Formula-Cookbook) and
[tap maintenance guide](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap).

After publication:

```bash
brew tap araujota/tap
brew audit --strict --online araujota/tap/vladder
brew install --build-from-source araujota/tap/vladder
brew test araujota/tap/vladder
vladder doctor
```

## Post-Publication Verification

```bash
python3 -m pip install --isolated --no-cache-dir 'vladder==<VERSION>'
vladder --version
vladder schema list
vladder lower validate
vladder skill validate
gh release download v<VERSION>
sha256sum -c SHA256SUMS
```

Update `release/channels.toml` only from observed account state. A successful publication means the
audited package and workflows are reproducible. It does not enlarge any proof boundary or create a
performance claim for an unmeasured workload.
