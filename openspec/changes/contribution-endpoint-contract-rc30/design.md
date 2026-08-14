# Design

The Convex health response becomes the authoritative, side-effect-free compatibility descriptor.
It names the endpoint-contract version, accepted review and training schemas, and submission routes.
The Python transport compares that descriptor with its packaged constants before acquiring a scoped
capability or sending a payload. Legacy services that omit the descriptor fail with an actionable
contract mismatch.

`vladder contribution doctor` performs the same check before its authorization probes. Online
release readiness validates the exact descriptor rather than accepting a generic healthy response.
Route-presence probes remain part of the doctor because they verify deployed routing as well as
advertised metadata.

The release process deploys the Convex source and verifies the public service before tagging rc30.
Unit tests use mocked HTTP responses; the release verification uses the real endpoint.
