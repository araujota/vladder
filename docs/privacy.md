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
  durable `agent_experience_review` opt-in, `--confirm-upload`, and record-level consent;
- `vladder training submit` sends one schema-validated model-training v3 search bundle only
  after independent durable `canonical_training_data` opt-in and the same per-record and
  per-command gates.

Durable decisions live at `$VLADDER_CONSENT_FILE`, or by default
`$XDG_CONFIG_HOME/vladder/consent.json` (`~/.config/vladder/consent.json` when XDG is unset). The
file is owner-readable/writable and is deliberately outside the package installation so decisions
survive upgrades and separate agent sessions. Missing state is `unknown`, not opt-in. Agents must
present the complete scope notice and ask the user to explicitly opt in or opt out for each
independent scope. A saved opt-out prohibits upload and repeated prompting unless the user
explicitly requests reconsideration.

Training opt-in authorizes ongoing contribution at every eligible opportunity without repeated
questions. The current model-training policy sends bounded normalized graph nodes, edges and
topology; structured actions; parent/child search lineage; completeness authority; direct and
descendant utility; negative and positive proof/physical outcomes; search costs; and coarsened
hardware/workload descriptors. This is **pseudonymized structural data, not anonymous data**. A
distinctive graph may fingerprint an algorithm, and installation-secret HMAC identities link
related roots, searches, branches and observations within one identity epoch. Distinctive search
structure may also fingerprint an optimization strategy. A materially broader policy
invalidates an older training opt-in and requires a new informed decision. An unsupported eligible
form is reported as an export gap. Review opt-in only authorizes a periodic request, at most every
30 days. The exact review is still shown for submission approval.

The release endpoints are built into the package, but no shared credential is embedded. After the
relevant durable opt-in, a fresh host obtains a random scope-specific append capability and stores
it at `$VLADDER_CONTRIBUTION_CREDENTIAL_FILE`, or by default
`$XDG_CONFIG_HOME/vladder/contribution-credentials.json`, with mode `0600`. Registration and
submissions are rate-limited; records are idempotent, private by default, and enter moderation.
Endpoint environment variables may override the release service; a maintainer trusted-ingestion
token is optional and is never part of release artifacts.

Convex does not expose SQL-style RLS because clients do not connect to tables. Access is enforced
at the registered-function boundary: contributor capabilities are accepted only by their matching
HTTP append action; capability lookup and all table writes are internal mutations; training data
has no public read function; moderation requires an independent admin token; and the public review
query returns approved reviews only. The backend stores SHA-256 capability hashes, not bearer
tokens. Possessing `training:write` or `review:write` grants no Convex deployment credential or
direct database access.
`--validate-only` exercises remote schema acceptance without storing the record, but transmits the
payload and therefore requires the same durable opt-in.

Review records cannot contain source or raw artifact attachments. Model-training v3 bundles contain
bounded normalized graph topology, public semantic vocabulary, structured grammar actions, search
lineage, coverage authority, descendant-survival labels, proof dispositions, and measurement labels.
Source text, paths, symbols, user-defined type names, raw
literals, raw artifacts, prompts, and declared personal data are excluded. Graph node IDs are
locally remapped; project/root/search/branch links use an installation-secret HMAC rather than public
source hashes. Unknown source-defined vocabulary is collapsed to public `other` categories rather
than hashed into a dictionary target. The CLI never uploads a local prior store, compilation unit,
proof bundle, or arbitrary file.

Legacy `vladder-training-bundle-v1` and flat `vladder-model-training-bundle-v2` files remain locally
schema-valid for historical inspection, but no current producer emits them. Enqueue and submit reject
them, outbox flush quarantines pre-existing entries, and the hosted legacy endpoints return `410 Gone`
before reading or storing the body.

## Threat Model

Structural de-identification reduces disclosure but cannot guarantee anonymity against an attacker
who already knows a distinctive algorithm. Enterprises may keep training contribution disabled
while retaining all local optimization features. Do not place secrets in manifests, contribution
JSON, benchmark output, or public issue reports.
Review every generated record before changing `privacy.submission_consent` to true. Maintainers
may supply a trusted token through `VLADDER_CONTRIBUTION_TOKEN`; ordinary users do not need one.

Run `vladder contribution doctor` after opting into both scopes to test append-path resolution,
cross-scope denial, moderation denial, and private-read absence without storing a contribution.

External compilers, profilers, project test commands, and benchmark runners execute with the
current user's permissions. vLadder is not a sandbox. Use a container or isolated machine for
untrusted source and untrusted runner commands.
