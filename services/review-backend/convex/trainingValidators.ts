import { v } from "convex/values";

export const numericFeatureValidator = v.object({
  name: v.string(),
  value: v.number(),
});

export const categoricalFeatureValidator = v.object({
  name: v.string(),
  value: v.string(),
});

export const trainingExampleValidator = v.object({
  example_id: v.string(),
  semantic_root_hash: v.string(),
  candidate_hash: v.string(),
  language: v.union(
    v.literal("c"), v.literal("cpp"), v.literal("rust"), v.literal("zig"),
    v.literal("julia"), v.literal("cuda"), v.literal("spirv"), v.literal("other"),
  ),
  region_kind: v.string(),
  grammar_family: v.string(),
  grammar_rule: v.string(),
  numeric_features: v.array(numericFeatureValidator),
  categorical_features: v.array(categoricalFeatureValidator),
  evidence: v.object({
    semantic_outcome: v.union(
      v.literal("inapplicable"), v.literal("missing_contract"),
      v.literal("semantic_mismatch"), v.literal("illegal"), v.literal("proof_failed"),
      v.literal("proof_unknown"), v.literal("proof_passed"),
    ),
    physical_outcome: v.union(
      v.literal("not_measured"), v.literal("compiler_identical"),
      v.literal("measured_regression"), v.literal("statistical_tie"),
      v.literal("small_win_below_floor"), v.literal("material_regional_win"),
      v.literal("composed_regression"), v.literal("composed_win"),
      v.literal("resource_regression"),
    ),
    proof_class: v.string(),
    quality_grade: v.union(v.literal("A"), v.literal("B"), v.literal("C"), v.literal("D")),
    benchmark_scope: v.union(
      v.literal("none"), v.literal("micro"), v.literal("regional"),
      v.literal("composed"), v.literal("end_to_end"),
    ),
    speedup_percent: v.union(v.number(), v.null()),
    ci_lower_percent: v.union(v.number(), v.null()),
    ci_upper_percent: v.union(v.number(), v.null()),
    sample_count: v.number(),
  }),
});

export const trainingBundleValidator = v.object({
  schema_version: v.literal("vladder-training-bundle-v1"),
  bundle_id: v.string(),
  created_at: v.string(),
  vladder_version: v.string(),
  producer: v.object({
    agent: v.string(),
    model: v.string(),
    provider: v.union(v.string(), v.null()),
  }),
  dataset: v.object({
    project_id: v.string(),
    grammar_version: v.string(),
    grammar_hash: v.string(),
    hardware_class: v.string(),
    hardware_manifest_hash: v.string(),
  }),
  examples: v.array(trainingExampleValidator),
  privacy: v.object({
    source_included: v.literal(false),
    raw_artifacts_included: v.literal(false),
    prompts_included: v.literal(false),
    personal_data_included: v.literal(false),
    submission_consent: v.literal(true),
  }),
});
