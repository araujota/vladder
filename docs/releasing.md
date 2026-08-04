# Releasing vLadder

## One-Time Repository Setup

1. Create the public GitHub repository and push this tree on `main`.
2. Protect `main` and require the `CI` workflow.
3. Create GitHub environments named `testpypi`, `pypi`, and `homebrew`. Require approval for
   `pypi` and `homebrew`.
4. On PyPI and TestPyPI, configure GitHub Trusted Publishers for this repository, workflow
   `release.yml` or `test-publish.yml`, and the matching environment.
5. Create a tap named `<owner>/homebrew-tap`. Set repository variable
   `HOMEBREW_TAP_REPOSITORY=<owner>/homebrew-tap` and environment secret
   `HOMEBREW_TAP_TOKEN` with write access to that tap. Leave the variable unset to receive a
   formula artifact without automatically updating a tap.

PyPI publication uses OIDC. Do not add `PYPI_API_TOKEN` or credentials to the repository.

## Release Procedure

1. Update `CHANGELOG.md`, `pyproject.toml`, `vladder/__init__.py`, README, and the release version
   assertion in `tests/test_release_vladder.py`.
2. Run:

   ```bash
   python3 scripts/release_preflight.py --repository OWNER/REPOSITORY
   python3 scripts/audit_release.py --root .
   python3 -m pytest -q
   openspec validate lifetime-aware-realization-v1 --strict
   python3 -m vladder lifetime evaluate-corpus \
     --manifest examples/lifetime/lifetime_corpus.yaml \
     --trace examples/lifetime/lifetime_trace.json \
     --out-dir /tmp/vladder-lifetime-release-evaluation
   python3 -m build
   python3 -m twine check dist/*
   python3 scripts/audit_release.py --artifact dist/*.whl --artifact dist/*.tar.gz
   python3 scripts/release_preflight.py --repository OWNER/REPOSITORY --require-artifacts
   ```

3. Exercise TestPyPI with the manual `TestPyPI` workflow.
4. Commit the release changes, create an annotated tag matching the package version, and push:

   ```bash
   git tag -a v1.0.0rc4 -m "vLadder 1.0.0rc4"
   git push origin main v1.0.0rc4
   ```

5. The `Release` workflow validates the tag, builds once, generates checksums and `vladder.rb`,
   creates the GitHub prerelease, publishes the same Python distributions to PyPI, and optionally
   updates the tap.

## Verification

After publication:

```bash
python3 -m pip install --isolated --no-cache-dir vladder==1.0.0rc4
vladder doctor
vladder skill validate
gh release download v1.0.0rc4
sha256sum -c SHA256SUMS
```

For the tap, run `brew audit --strict --online OWNER/tap/vladder`, install it in a clean runner,
and execute `brew test OWNER/tap/vladder`. Homebrew installs the package and core LLVM/Z3 tools;
strict Alive2/perf availability remains platform-specific and is reported by `vladder doctor`.

## Release Claim

A successful publication means the audited package and workflow are reproducible. It does not
convert research-only grammar routes into automatic source lowerers or create a performance claim
for a workload that was not measured.
