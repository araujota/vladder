import { v } from "convex/values";

const numericFeature = v.object({ name: v.string(), value: v.number() });
const categoricalFeature = v.object({ name: v.string(), value: v.string() });
const featureSet = v.object({ numeric: v.array(numericFeature), categorical: v.array(categoricalFeature) });
const nullableNumber = v.union(v.number(), v.null());

const graphNode = v.object({
  index: v.number(), kind: v.string(), operation: v.string(),
  type_class: v.union(
    v.literal("boolean"), v.literal("integer"), v.literal("float"), v.literal("pointer"),
    v.literal("aggregate"), v.literal("unknown"), v.literal("other"),
  ),
  bit_width: nullableNumber, vector_lanes: nullableNumber,
  numeric_features: v.array(numericFeature), categorical_features: v.array(categoricalFeature),
});
const graphEdge = v.object({
  source: v.number(), destination: v.number(), relation: v.string(), ordering: v.string(),
  numeric_features: v.array(numericFeature), categorical_features: v.array(categoricalFeature),
});
const modelRoot = v.object({
  root_id: v.string(), project_id: v.string(), graph_version: v.string(),
  languages: v.array(v.union(
    v.literal("c"), v.literal("cpp"), v.literal("rust"), v.literal("zig"), v.literal("julia"),
    v.literal("cuda"), v.literal("spirv"), v.literal("other"),
  )),
  graph: v.object({
    nodes: v.array(graphNode), edges: v.array(graphEdge),
    obligations: v.array(v.object({ category: v.string(), scope: v.string(), proof_method: v.string() })),
    effects: v.array(v.object({ kind: v.string(), phase: v.string(), ordering: v.string() })),
    protocols: v.array(v.object({ kind: v.string() })),
    claims: v.array(v.object({ status: v.string(), scope: v.string() })),
  }),
  contract_features: featureSet,
});
const action = v.object({
  family: v.string(), family_version: v.string(), primitives: v.array(v.string()),
  numeric_parameters: v.array(numericFeature), categorical_parameters: v.array(categoricalFeature),
  extension_namespaces: v.array(v.string()),
});
const stageCoverage = v.union(
  v.literal("not_attempted"), v.literal("partial"), v.literal("complete"), v.literal("soundly_closed"),
);
const utility = v.object({
  proof_valid: v.boolean(), distinct_realization: v.boolean(), physically_material: v.boolean(),
  retained: v.boolean(), promoted: v.boolean(),
});
const nullableBoolean = v.union(v.boolean(), v.null());
const descendantUtility = v.object({
  proof_valid: nullableBoolean, distinct_realization: nullableBoolean, physically_material: nullableBoolean,
  retained: nullableBoolean, promoted: nullableBoolean, useful: nullableBoolean,
  target_definition: v.literal("proof-valid-or-stronger-v1"),
});

export const searchTrainingBundleValidator = v.object({
  schema_version: v.literal("vladder-model-training-bundle-v3"),
  bundle_id: v.string(), created_at: v.string(), vladder_version: v.string(),
  producer: v.object({ agent: v.string(), model: v.string(), provider: v.union(v.string(), v.null()) }),
  dataset: v.object({
    grammar_version: v.string(), grammar_hash: v.string(),
    canonicalizer_version: v.literal("search-pruner-graph-v3"),
    labeler_version: v.literal("useful-descendant-v1"),
    target_definition: v.literal("proof-valid-or-stronger-v1"), identity_epoch: v.string(),
  }),
  roots: v.array(modelRoot),
  searches: v.array(v.object({
    search_id: v.string(), root_id: v.string(), root_branch_id: v.string(), grammar_version: v.string(),
    grammar_hash: v.string(),
    selection_policy: v.union(
      v.literal("exhaustive"), v.literal("bounded_exhaustive"), v.literal("heuristic"),
      v.literal("model_guided"), v.literal("manual"), v.literal("terminal_workflow_import"),
      v.literal("flat_prior_import"),
    ),
    coverage: v.union(
      v.literal("complete"), v.literal("soundly_pruned"), v.literal("partial"),
      v.literal("truncated"), v.literal("interrupted"), v.literal("not_started"),
    ),
    stage_coverage: v.object({
      grammar_family: stageCoverage, candidate_family: stageCoverage,
      composition: stageCoverage, cross_tu: stageCoverage,
    }),
    fragment: v.object({
      kind: v.union(v.literal("full_trace"), v.literal("complete_subtree"), v.literal("partial_snapshot")),
      external_parent_branch_id: v.union(v.string(), v.null()),
    }),
    exploration_reserve_fraction: v.number(), hardware: featureSet, workload: featureSet,
  })),
  branches: v.array(v.object({
    branch_id: v.string(), search_id: v.string(), parent_branch_id: v.union(v.string(), v.null()),
    depth: v.number(),
    stage: v.union(
      v.literal("baseline"), v.literal("grammar_family"), v.literal("candidate_family"),
      v.literal("composition"), v.literal("cross_tu"),
    ),
    baseline: v.boolean(), action,
    state: v.union(
      v.literal("enumerated"), v.literal("expanded"), v.literal("terminal"), v.literal("blocked"),
      v.literal("pruned_sound"), v.literal("pruned_heuristic"), v.literal("duplicate"),
      v.literal("compiler_identical"), v.literal("interrupted"),
    ),
    evidence_coverage: v.union(v.literal("none"), v.literal("partial"), v.literal("complete"), v.literal("soundly_blocked")),
    coverage: v.object({
      children_status: v.union(
        v.literal("not_applicable"), v.literal("not_enumerated"), v.literal("partially_enumerated"),
        v.literal("exhaustive"), v.literal("soundly_closed"),
      ),
      emitted_child_count: v.number(), expected_child_count: nullableNumber,
      completeness_reason: v.union(
        v.literal("terminal"), v.literal("exhaustive_grammar"), v.literal("sound_contract"),
        v.literal("sound_legality"), v.literal("sound_dominance"), v.literal("budget"),
        v.literal("time"), v.literal("interrupted"), v.literal("not_applicable"), v.literal("unknown"),
      ),
      soundness_proof_class: v.string(),
    }),
    search_cost: v.object({
      node_expansions: nullableNumber, compiler_invocations: nullableNumber, proof_calls: nullableNumber,
      benchmark_runs: nullableNumber, elapsed_ms: nullableNumber,
    }),
    direct_utility: utility, descendant_utility: descendantUtility,
    survival: v.object({
      class: v.union(
        v.literal("KEEP"), v.literal("KEEP_UNCERTAIN"), v.literal("PRUNE_HIGH_CONFIDENCE"),
        v.literal("BLOCKED_BY_CONTRACT"),
      ),
      authority: v.union(
        v.literal("baseline_guard"), v.literal("observed_positive_path"),
        v.literal("derived_complete_tree"), v.literal("sound_contract"), v.literal("incomplete_tree"),
      ),
      positive_descendant_count: v.number(), label_version: v.literal("useful-descendant-v1"),
    }),
  })),
  observations: v.array(v.object({
    observation_id: v.string(), branch_id: v.string(),
    kind: v.union(
      v.literal("grammar_disposition"), v.literal("proof"), v.literal("differential"),
      v.literal("compilation"), v.literal("assembly"), v.literal("static_cost"),
      v.literal("benchmark"), v.literal("hardware_counter"), v.literal("composition"),
      v.literal("retention"), v.literal("search"),
    ),
    outcome: v.union(
      v.literal("inapplicable"), v.literal("missing_contract"), v.literal("semantic_mismatch"),
      v.literal("illegal"), v.literal("proof_failed"), v.literal("proof_unknown"),
      v.literal("proof_passed"), v.literal("distinct_realization"), v.literal("duplicate"),
      v.literal("compiler_identical"), v.literal("dominated_sound"),
      v.literal("exhausted_no_useful_descendant"), v.literal("measured_regression"),
      v.literal("statistical_tie"), v.literal("small_win_below_floor"),
      v.literal("material_regional_win"), v.literal("composed_regression"), v.literal("composed_win"),
      v.literal("retained_candidate"), v.literal("promoted_candidate"), v.literal("resource_regression"),
      v.literal("search_truncated"), v.literal("search_interrupted"),
    ),
    quality_grade: v.union(v.literal("A"), v.literal("B"), v.literal("C"), v.literal("D")),
    proof_class: v.string(),
    benchmark_scope: v.union(
      v.literal("none"), v.literal("micro"), v.literal("regional"),
      v.literal("composed"), v.literal("end_to_end"),
    ),
    speedup_percent: nullableNumber, ci_lower_percent: nullableNumber, ci_upper_percent: nullableNumber,
    sample_count: v.number(), resource_features: featureSet,
  })),
  privacy: v.object({
    profile_version: v.literal("enterprise-graph-deidentification-v1"),
    risk_classification: v.literal("pseudonymized_structural_data"),
    identity_scheme: v.literal("hmac-sha256-consent-epoch"), identity_epoch: v.string(),
    topology_included: v.literal(true), search_lineage_included: v.literal(true),
    source_included: v.literal(false), source_identifiers_included: v.literal(false),
    raw_literals_included: v.literal(false), raw_artifacts_included: v.literal(false),
    prompts_included: v.literal(false), personal_data_included: v.literal(false),
    submission_consent: v.literal(true),
    residual_risks: v.array(v.union(
      v.literal("algorithm_topology_fingerprinting"), v.literal("within_epoch_record_linkability"),
      v.literal("search_strategy_fingerprinting"),
    )),
  }),
});
