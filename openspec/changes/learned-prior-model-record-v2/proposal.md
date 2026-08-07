## Why

The production `vladder-training-bundle-v1` schema flattens an optimization result into opaque
hashes, pooled features, and terminal labels. Those records are useful telemetry, but they cannot
train the intended graph prior because graph topology, structured grammar actions, hardware and
workload context, and candidate-relative observations cannot be reconstructed.

Program-graph learning and learned autotuning both treat the graph and candidate configuration as
model inputs. ProGraML uses a directed attributed multigraph over program relations, while learned
TPU cost models pair computation graphs and configurations with measured outcomes. The vLadder
record must preserve the equivalent language-neutral information-flow structure.

The richer structure also changes disclosure risk. NIST SP 800-188 warns that repeatable hashing
is pseudonymization, not sufficient de-identification by itself. Existing training opt-ins therefore
cannot silently authorize topology disclosure.

## What Changes

- Add `vladder-model-training-bundle-v2` with normalized semantic roots, bounded attributed graph
  topology, structured candidate actions, hardware/workload descriptors, and append-only
  observations.
- Add an enterprise de-identification profile that removes source identifiers and literals, maps
  nodes to local integer IDs, exposes only public vLadder vocabulary, buckets potentially sensitive
  numeric descriptors, and uses consent-epoch HMAC identities.
- Keep v1 workflow telemetry separate and explicitly non-model-ready.
- Add v2 export, validation, submission, ingestion, and Convex storage without exposing a public
  training read path.
- Version training consent. Prior training decisions become unknown because graph topology and
  linkable candidate groups are a materially broader disclosure; review consent remains independent.
- Feed v2 bundles into the existing root-grouped prior store and model interface, preserving the
  baseline, exploration reserve, proof gates, and physical measurement authority.

## Impact

Future contributions become directly usable for graph/action/hardware/workload ranking. Historical
v1 records remain auxiliary telemetry and cannot be reverse-expanded into graph roots. Enterprise
users receive an accurate disclosure notice: records are source-free and de-identified, but
structural topology remains pseudonymous data with residual fingerprinting risk.
