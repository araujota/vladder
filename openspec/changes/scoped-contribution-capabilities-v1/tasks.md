# Tasks

## 1. Backend

- [x] 1.1 Add hashed, revocable, scope-specific contributor capabilities.
- [x] 1.2 Add rate-limited capability registration and scoped append authorization.
- [x] 1.3 Preserve separate admin moderation and private-by-default records.

## 2. Client

- [x] 2.1 Bootstrap missing credentials only after durable scope opt-in.
- [x] 2.2 Persist credentials atomically with owner-only permissions outside the package.
- [x] 2.3 Retry once for revoked automatically managed credentials without exposing tokens.

## 3. Conformance

- [x] 3.1 Test both append scopes, cross-scope denial, moderation denial, and private-read absence.
- [x] 3.2 Deploy the backend and run fresh-host live probes without retaining contribution records.
- [x] 3.3 Update release, privacy, service, and skill documentation.
