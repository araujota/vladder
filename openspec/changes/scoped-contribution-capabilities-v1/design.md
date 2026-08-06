# Design

## Distribution Boundary

No reusable backend secret is embedded in a wheel, source archive, Homebrew formula, skill, or
repository. A fresh installation obtains a random opaque capability from the release service only
after the corresponding durable contribution scope is opted in. The token is stored in the user's
configuration directory with owner-only permissions.

## Authorization Boundary

Convex does not expose database tables through a SQL-style RLS surface. The equivalent enforcement
boundary is the registered function and HTTP-action surface. Public HTTP actions may register a
bounded contributor capability and append a schema-valid record. Table writes, capability lookup,
moderation, and private data access use internal functions. A capability cannot invoke internal
functions or Convex deployment APIs.

Capabilities are scope-specific. `training:write` cannot submit a review and `review:write` cannot
submit training data. Neither scope can list pending records, approve records, mutate an existing
record, or access administration routes.

## Credential Lifecycle

The server generates 256 bits of randomness and stores only SHA-256(token). Clients store one token
per endpoint and scope. Invalid or revoked automatically managed credentials are discarded and may
be reissued once. Explicit environment credentials are never rewritten automatically.

## Abuse And Privacy Controls

Registration and append operations remain rate limited. Record validators, size bounds, privacy
literals, moderation defaults, idempotent record IDs, and durable local consent remain independent
fail-closed gates. Registration transmits only the requested scope and client version.

## Conformance

The release probe checks service health, obtains both scope-specific capabilities, verifies each
against its own endpoint, confirms cross-scope denial, confirms unauthenticated moderation denial,
and confirms that no private training read route exists. It never stores a review or training
record.
