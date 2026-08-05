import { v } from "convex/values";

export const stringList = v.array(v.string());

export const agentReviewValidator = v.object({
  schema_version: v.literal("vladder-agent-review-v1"),
  canonical_prompt_version: v.literal("vladder-agent-review-prompt-v1"),
  review_id: v.string(),
  created_at: v.string(),
  vladder_version: v.string(),
  reviewer: v.object({
    agent: v.string(),
    model: v.string(),
    provider: v.union(v.string(), v.null()),
  }),
  project: v.object({
    name: v.string(),
    repository: v.union(v.string(), v.null()),
    revision: v.string(),
  }),
  scope: v.object({
    summary: v.string(),
    languages: v.array(v.string()),
    region_count: v.number(),
    workload: v.string(),
  }),
  evidence: v.object({
    promotion_summary_sha256: v.string(),
    proof_class: v.string(),
    artifact_schema_versions: v.array(v.string()),
    benchmark_summary: v.string(),
  }),
  assessment: v.object({
    rating: v.number(),
    outcome: v.union(
      v.literal("retained_win"),
      v.literal("verified_negative"),
      v.literal("partial_evidence"),
      v.literal("workflow_failure"),
      v.literal("revalidation"),
    ),
    claim: v.string(),
    strengths: stringList,
    limitations: stringList,
    rejected_candidates: stringList,
    unresolved_boundaries: stringList,
    recommendations: stringList,
  }),
  privacy: v.object({
    source_included: v.literal(false),
    raw_artifacts_included: v.literal(false),
    submission_consent: v.literal(true),
  }),
});
