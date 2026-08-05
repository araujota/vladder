## 1. Consent Authority

- [x] 1.1 Add independent durable training and review scopes with unknown-by-default behavior.
- [x] 1.2 Atomically persist explicit opt-in/opt-out outside the package with owner-only access.
- [x] 1.3 Add CLI inspection and explicit decision recording.

## 2. Workflow Integration

- [x] 2.1 Require durable opt-in before training, review, and remote validate-only requests.
- [x] 2.2 Preserve exact-record consent and command confirmation.
- [x] 2.3 Expose non-executing optional stages in agent and learned-prior summaries.

## 3. Agent Contract

- [x] 3.1 Compel explicit opt-in/opt-out clarification for unknown state.
- [x] 3.2 Suppress repeated prompts and uploads after opt-out.
- [x] 3.3 Document persistence, independent scopes, and exact payload review.

## 4. Verification

- [x] 4.1 Pass persistence, scope, no-network, and three-gate Python tests.
- [x] 4.2 Pass skill, schema, package, and strict OpenSpec validation.
- [x] 4.3 Pass Convex TypeScript checks without making a live contribution.
