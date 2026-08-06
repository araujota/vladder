## 1. Consent Authority

- [x] 1.1 Add independent durable training and review scopes with unknown-by-default behavior.
- [x] 1.2 Atomically persist explicit opt-in/opt-out outside the package with owner-only access.
- [x] 1.3 Add CLI inspection and explicit decision recording.

## 2. Workflow Integration

- [x] 2.1 Require durable opt-in before training, review, and remote validate-only requests.
- [x] 2.2 Preserve exact-record consent and command confirmation.
- [x] 2.3 Expose blocked, continuous-training, periodic-review, and failed-sync states in summaries.

## 3. Agent Contract

- [x] 3.1 Compel explicit opt-in/opt-out clarification for unknown state.
- [x] 3.2 Suppress repeated prompts and uploads after opt-out.
- [x] 3.3 Document persistence, independent scopes, and exact payload review.
- [x] 3.4 Present complete informed-decision notices and enforce periodic review cadence.
- [x] 3.5 Export canonical prior evidence into the bounded anonymized training schema.

## 4. Verification

- [x] 4.1 Pass persistence, scope, no-network, continuous-sync, and periodic-cadence Python tests.
- [x] 4.2 Pass skill, schema, package, and strict OpenSpec validation.
- [x] 4.3 Pass Convex TypeScript/development-deployment checks without making a live contribution.
