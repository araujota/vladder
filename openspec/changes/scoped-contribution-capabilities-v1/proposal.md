# Scoped Contribution Capabilities v1

## Why

The public contribution endpoints currently isolate writes through Convex HTTP actions and internal
mutations, but fresh installations do not possess an explicit least-privilege identity. Shipping a
shared secret would be extractable and would couple contribution access to broader backend access.

## What Changes

- Issue random installation-scoped capabilities from a bounded public registration route.
- Grant each capability exactly one append scope: `training:write` or `review:write`.
- Persist only capability hashes in Convex and owner-protected tokens outside the installed package.
- Require a valid scoped capability for contribution validation and storage.
- Keep moderation operations separately admin-authenticated and all contribution writes private by
  default.
- Add a conformance probe proving that both append paths resolve while private reads and moderation
  remain inaccessible.
