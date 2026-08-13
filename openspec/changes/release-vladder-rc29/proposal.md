# Release vLadder rc29

## Why

Production canonical-state search and its training traces exist in the working tree but the
installable package does not yet bind the engine, qualification evidence, model-data authority,
documentation, and publication surfaces into one release identity.

## What Changes

- Bundle and validate canonical-search qualification evidence in the Python distribution.
- Fail closed when composition-native training traces have inconsistent state, frontier, terminal,
  label, cost-readiness, summary, or hash metadata.
- Keep post-search outcomes outside inference features and preserve ML as ordering/proposal only.
- Align CLI, README, agent skill, schemas, CI, release workflow, and release-site copy.
- Publish one source identity through main, GitHub Release, PyPI, and Vercel.

## Non-Claims

The release artifact records bounded qualification; it does not prove global search optimality.
Training readiness does not grant learned deletion authority or make incomplete traces exhaustive.
