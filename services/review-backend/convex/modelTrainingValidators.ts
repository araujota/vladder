import { v } from "convex/values";

const numericFeature = v.object({ name: v.string(), value: v.number() });
const categoricalFeature = v.object({ name: v.string(), value: v.string() });
const featureSet = v.object({
  numeric: v.array(numericFeature),
  categorical: v.array(categoricalFeature),
});

const graphNode = v.object({
  index: v.number(),
  kind: v.string(),
  operation: v.string(),
  type_class: v.union(
    v.literal("boolean"), v.literal("integer"), v.literal("float"),
    v.literal("pointer"), v.literal("aggregate"), v.literal("unknown"), v.literal("other"),
  ),
  bit_width: v.union(v.number(), v.null()),
  vector_lanes: v.union(v.number(), v.null()),
  numeric_features: v.array(numericFeature),
  categorical_features: v.array(categoricalFeature),
});

const graphEdge = v.object({
  source: v.number(),
  destination: v.number(),
  relation: v.string(),
  ordering: v.string(),
  numeric_features: v.array(numericFeature),
  categorical_features: v.array(categoricalFeature),
});

const modelRoot = v.object({
  root_id: v.string(),
  project_id: v.string(),
  graph_version: v.string(),
  languages: v.array(v.union(
    v.literal("c"), v.literal("cpp"), v.literal("rust"), v.literal("zig"),
    v.literal("julia"), v.literal("cuda"), v.literal("spirv"), v.literal("other"),
  )),
  graph: v.object({
    nodes: v.array(graphNode),
    edges: v.array(graphEdge),
    obligations: v.array(v.object({ category: v.string(), scope: v.string(), proof_method: v.string() })),
    effects: v.array(v.object({ kind: v.string(), phase: v.string(), ordering: v.string() })),
    protocols: v.array(v.object({ kind: v.string() })),
    claims: v.array(v.object({ status: v.string(), scope: v.string() })),
  }),
  contract_features: featureSet,
});

const modelCandidate = v.object({
  candidate_id: v.string(),
  root_id: v.string(),
  baseline: v.boolean(),
  action: v.object({
    family: v.string(),
    family_version: v.string(),
    primitives: v.array(v.string()),
    numeric_parameters: v.array(numericFeature),
    categorical_parameters: v.array(categoricalFeature),
    extension_namespaces: v.array(v.string()),
  }),
  hardware: featureSet,
  workload: featureSet,
});

const modelObservation = v.object({
  observation_id: v.string(),
  candidate_id: v.string(),
  kind: v.union(
    v.literal("grammar_disposition"), v.literal("proof"), v.literal("differential"),
    v.literal("compilation"), v.literal("assembly"), v.literal("static_cost"),
    v.literal("benchmark"), v.literal("hardware_counter"), v.literal("composition"),
  ),
  outcome: v.union(
    v.literal("inapplicable"), v.literal("missing_contract"), v.literal("semantic_mismatch"),
    v.literal("illegal"), v.literal("proof_failed"), v.literal("proof_unknown"),
    v.literal("proof_passed"), v.literal("compiler_identical"), v.literal("measured_regression"),
    v.literal("statistical_tie"), v.literal("small_win_below_floor"),
    v.literal("material_regional_win"), v.literal("composed_regression"),
    v.literal("composed_win"), v.literal("resource_regression"),
  ),
  quality_grade: v.union(v.literal("A"), v.literal("B"), v.literal("C"), v.literal("D")),
  proof_class: v.string(),
  benchmark_scope: v.union(
    v.literal("none"), v.literal("micro"), v.literal("regional"),
    v.literal("composed"), v.literal("end_to_end"),
  ),
  speedup_percent: v.union(v.number(), v.null()),
  ci_lower_percent: v.union(v.number(), v.null()),
  ci_upper_percent: v.union(v.number(), v.null()),
  sample_count: v.number(),
  resource_features: featureSet,
});

export const modelTrainingBundleValidator = v.object({
  schema_version: v.literal("vladder-model-training-bundle-v2"),
  bundle_id: v.string(),
  created_at: v.string(),
  vladder_version: v.string(),
  producer: v.object({
    agent: v.string(), model: v.string(), provider: v.union(v.string(), v.null()),
  }),
  dataset: v.object({
    grammar_version: v.string(),
    grammar_hash: v.string(),
    canonicalizer_version: v.literal("model-ready-graph-v2"),
    identity_epoch: v.string(),
  }),
  roots: v.array(modelRoot),
  candidates: v.array(modelCandidate),
  observations: v.array(modelObservation),
  privacy: v.object({
    profile_version: v.literal("enterprise-graph-deidentification-v1"),
    risk_classification: v.literal("pseudonymized_structural_data"),
    identity_scheme: v.literal("hmac-sha256-consent-epoch"),
    identity_epoch: v.string(),
    topology_included: v.literal(true),
    source_included: v.literal(false),
    source_identifiers_included: v.literal(false),
    raw_literals_included: v.literal(false),
    raw_artifacts_included: v.literal(false),
    prompts_included: v.literal(false),
    personal_data_included: v.literal(false),
    submission_consent: v.literal(true),
    residual_risks: v.array(v.union(
      v.literal("algorithm_topology_fingerprinting"),
      v.literal("within_epoch_record_linkability"),
    )),
  }),
});
