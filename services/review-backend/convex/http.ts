import { httpRouter } from "convex/server";
import type { Infer } from "convex/values";
import { httpAction } from "./_generated/server";
import { api, internal } from "./_generated/api";
import { agentReviewValidator } from "./reviewValidators";
import { searchTrainingBundleValidator } from "./searchTrainingValidators";

type AgentReview = Infer<typeof agentReviewValidator>;
type SearchTrainingBundle = Infer<typeof searchTrainingBundleValidator>;
type SubmissionKind = "review" | "training" | "credential";
type CapabilityScope = "review:write" | "training:write";

const MAX_PAYLOAD_BYTES = 768 * 1024;
const DAILY_LIMITS: Record<SubmissionKind, number> = { review: 20, training: 10_000, credential: 10 };
const HASH_PATTERN = /^[a-f0-9]{64}$/;
const TOKEN_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:+/-]{0,95}$/;

const http = httpRouter();

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function trustedSubmission(request: Request): boolean {
  const authorization = request.headers.get("authorization");
  const expected = process.env.VLADDER_REVIEW_TOKEN;
  return Boolean(expected) && authorization === `Bearer ${expected}`;
}

function randomCapability(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return `vc1_${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

async function authorizeSubmission(
  ctx: Parameters<Parameters<typeof httpAction>[0]>[0], request: Request, requiredScope: CapabilityScope,
): Promise<{ allowed: boolean; trusted: boolean; reason: string; rateLimitIdentity: string | null }> {
  if (trustedSubmission(request)) {
    return { allowed: true, trusted: true, reason: "trusted_ingestion", rateLimitIdentity: null };
  }
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer vc1_")) {
    return { allowed: false, trusted: false, reason: "contributor_credential_required", rateLimitIdentity: null };
  }
  const token = authorization.slice("Bearer ".length);
  const result = await ctx.runMutation(internal.contributors.authorize, {
    tokenHash: await sha256(token),
    requiredScope,
  });
  return {
    allowed: result.allowed,
    trusted: false,
    reason: result.reason,
    rateLimitIdentity: result.credentialId,
  };
}

async function consumePublicLimit(
  ctx: Parameters<Parameters<typeof httpAction>[0]>[0],
  request: Request,
  kind: SubmissionKind,
  capabilityIdentity: string | null = null,
) {
  const pepper = process.env.VLADDER_SUBMISSION_PEPPER;
  if (!pepper) {
    throw new Error("public submission service is not configured");
  }
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const address = request.headers.get("cf-connecting-ip") ?? forwarded ?? "unavailable";
  const userAgent = (request.headers.get("user-agent") ?? "unknown").slice(0, 200);
  const identity = capabilityIdentity === null
    ? `network:${address}:${userAgent}`
    : `capability:${capabilityIdentity}`;
  const fingerprintHash = await sha256(`${pepper}:${identity}`);
  const bucket = new Date().toISOString().slice(0, 10);
  return await ctx.runMutation(internal.rateLimits.consume, {
    fingerprintHash,
    bucket,
    kind,
    limit: DAILY_LIMITS[kind],
  });
}

async function readBoundedJson(request: Request): Promise<{ text: string; value: unknown } | Response> {
  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > MAX_PAYLOAD_BYTES) {
    return jsonResponse({ error: "payload exceeds 768 KiB" }, 413);
  }
  try {
    return { text, value: JSON.parse(text) as unknown };
  } catch {
    return jsonResponse({ error: "invalid JSON" }, 400);
  }
}

function reviewBounds(review: AgentReview): string | null {
  if (review.assessment.rating < 0 || review.assessment.rating > 10) return "rating must be between 0 and 10";
  if (review.scope.region_count < 0 || !Number.isInteger(review.scope.region_count)) return "region_count must be a nonnegative integer";
  const lists = [
    review.scope.languages,
    review.evidence.artifact_schema_versions,
    review.assessment.strengths,
    review.assessment.limitations,
    review.assessment.rejected_candidates,
    review.assessment.unresolved_boundaries,
    review.assessment.recommendations,
  ];
  if (lists.some((items) => items.length > 100)) return "review list exceeds 100 items";
  if (!HASH_PATTERN.test(review.evidence.promotion_summary_sha256)) return "invalid promotion summary hash";
  return null;
}

function searchTrainingBounds(bundle: SearchTrainingBundle): string | null {
  if (bundle.roots.length < 1 || bundle.roots.length > 16) return "roots must contain 1 to 16 records";
  if (bundle.searches.length < 1 || bundle.searches.length > 32) return "searches must contain 1 to 32 records";
  if (bundle.branches.length < 1 || bundle.branches.length > 1024) return "branches must contain 1 to 1024 records";
  if (bundle.observations.length > 4096) return "observations exceed 4096 records";
  if (bundle.dataset.identity_epoch !== bundle.privacy.identity_epoch) return "identity epoch mismatch";
  if (!HASH_PATTERN.test(bundle.dataset.grammar_hash)) return "invalid grammar hash";
  const featuresValid = (features: { numeric: Array<{ name: string }>; categorical: Array<{ name: string; value: string }> }) =>
    features.numeric.length <= 128 && features.categorical.length <= 128
    && features.numeric.every((item) => TOKEN_PATTERN.test(item.name))
    && features.categorical.every((item) => TOKEN_PATTERN.test(item.name) && TOKEN_PATTERN.test(item.value));
  const roots = new Set(bundle.roots.map((root) => root.root_id));
  const searches = new Map(bundle.searches.map((search) => [search.search_id, search]));
  const branches = new Map(bundle.branches.map((branch) => [branch.branch_id, branch]));
  for (const root of bundle.roots) {
    if (!HASH_PATTERN.test(root.root_id) || !HASH_PATTERN.test(root.project_id)) return "invalid root identity";
    if (root.graph.nodes.length < 1 || root.graph.nodes.length > 512) return "graph node count outside bounds";
    if (root.graph.edges.length > 2048) return "graph edge count outside bounds";
    if (root.graph.obligations.length > 128 || root.graph.effects.length > 128
      || root.graph.protocols.length > 64 || root.graph.claims.length > 128) return "graph annotation count outside bounds";
    if (!featuresValid(root.contract_features)) return "root feature count or token outside bounds";
    if (root.graph.nodes.some((node) => !TOKEN_PATTERN.test(node.kind) || !TOKEN_PATTERN.test(node.operation)
      || node.numeric_features.length > 64 || node.categorical_features.length > 32)) return "invalid graph node features";
    if (root.graph.edges.some((edge) => !TOKEN_PATTERN.test(edge.relation) || !TOKEN_PATTERN.test(edge.ordering)
      || edge.numeric_features.length > 64 || edge.categorical_features.length > 32)) return "invalid graph edge features";
    const nodeIds = new Set(root.graph.nodes.map((node) => node.index));
    if (nodeIds.size !== root.graph.nodes.length) return "duplicate graph node index";
    if (root.graph.edges.some((edge) => !nodeIds.has(edge.source) || !nodeIds.has(edge.destination))) {
      return "graph edge references an unknown node";
    }
  }
  if (searches.size !== bundle.searches.length || branches.size !== bundle.branches.length) return "duplicate search or branch identity";
  for (const search of bundle.searches) {
    if (!HASH_PATTERN.test(search.search_id) || !roots.has(search.root_id)) return "invalid search linkage";
    if (!HASH_PATTERN.test(search.grammar_hash) || !featuresValid(search.hardware) || !featuresValid(search.workload)) {
      return "search context outside bounds";
    }
    const rootBranch = branches.get(search.root_branch_id);
    if (!rootBranch || rootBranch.search_id !== search.search_id || rootBranch.parent_branch_id !== null) {
      return "invalid search root branch";
    }
    if (search.fragment.kind === "full_trace" && (rootBranch.depth !== 0 || !rootBranch.baseline)) {
      return "invalid full-trace root branch";
    }
    if (search.fragment.kind === "complete_subtree" && search.fragment.external_parent_branch_id === null) {
      return "complete subtree requires an external parent";
    }
  }
  const childCounts = new Map<string, number>();
  for (const branch of bundle.branches) {
    if (!HASH_PATTERN.test(branch.branch_id) || !searches.has(branch.search_id)) return "invalid branch linkage";
    if (!TOKEN_PATTERN.test(branch.action.family) || !TOKEN_PATTERN.test(branch.action.family_version)
      || branch.action.primitives.length > 64 || branch.action.numeric_parameters.length > 64
      || branch.action.categorical_parameters.length > 64 || branch.action.extension_namespaces.length > 8) {
      return "branch action outside bounds";
    }
    if (branch.parent_branch_id !== null) {
      const parent = branches.get(branch.parent_branch_id);
      if (!parent || parent.search_id !== branch.search_id || parent.depth + 1 !== branch.depth) return "invalid branch parent";
      childCounts.set(parent.branch_id, (childCounts.get(parent.branch_id) ?? 0) + 1);
    }
    if (branch.baseline && (branch.survival.class !== "KEEP" || branch.survival.authority !== "baseline_guard")) {
      return "baseline branch is not protected";
    }
    if (branch.survival.class === "PRUNE_HIGH_CONFIDENCE"
      && (branch.survival.authority !== "derived_complete_tree" || branch.descendant_utility.useful !== false)) {
      return "unsafe high-confidence prune label";
    }
    if (branch.survival.class === "BLOCKED_BY_CONTRACT"
      && (branch.survival.authority !== "sound_contract" || branch.evidence_coverage !== "soundly_blocked"
        || branch.coverage.children_status !== "soundly_closed")) return "unsafe contract-blocked label";
  }
  for (const branch of bundle.branches) {
    const actual = childCounts.get(branch.branch_id) ?? 0;
    if (branch.coverage.emitted_child_count !== actual) return "emitted child count mismatch";
    if (branch.coverage.children_status === "exhaustive" && branch.coverage.expected_child_count !== actual) {
      return "exhaustive branch child count mismatch";
    }
  }
  for (const observation of bundle.observations) {
    if (!HASH_PATTERN.test(observation.observation_id) || !branches.has(observation.branch_id)) {
      return "invalid observation linkage";
    }
    if (!Number.isInteger(observation.sample_count) || observation.sample_count < 0) return "invalid sample count";
    if (!featuresValid(observation.resource_features)) return "observation resources outside bounds";
  }
  const utilityKeys = [
    "proof_valid", "distinct_realization", "physically_material", "retained", "promoted",
  ] as const;
  type UtilityKey = typeof utilityKeys[number];
  type DerivedUtility = Record<UtilityKey, boolean | null>;
  const positiveOutcomes: Record<UtilityKey, Set<string>> = {
    proof_valid: new Set(["proof_passed", "material_regional_win", "composed_win", "retained_candidate", "promoted_candidate"]),
    distinct_realization: new Set([
      "distinct_realization", "measured_regression", "statistical_tie", "small_win_below_floor",
      "material_regional_win", "composed_regression", "composed_win", "resource_regression",
      "retained_candidate", "promoted_candidate",
    ]),
    physically_material: new Set(["material_regional_win", "composed_win", "retained_candidate", "promoted_candidate"]),
    retained: new Set(["retained_candidate", "promoted_candidate", "composed_win"]),
    promoted: new Set(["promoted_candidate"]),
  };
  const terminalNegativeOutcomes = new Set([
    "inapplicable", "semantic_mismatch", "illegal", "proof_failed", "duplicate",
    "compiler_identical", "dominated_sound", "exhausted_no_useful_descendant",
    "measured_regression", "statistical_tie", "small_win_below_floor",
    "composed_regression", "resource_regression",
  ]);
  const soundReasons = new Set(["sound_contract", "sound_legality", "sound_dominance"]);
  const observationOutcomes = new Map<string, Set<string>>();
  for (const observation of bundle.observations) {
    const outcomes = observationOutcomes.get(observation.branch_id) ?? new Set<string>();
    outcomes.add(observation.outcome);
    observationOutcomes.set(observation.branch_id, outcomes);
  }
  const children = new Map<string, string[]>();
  for (const branch of bundle.branches) {
    if (branch.parent_branch_id === null) continue;
    const childIds = children.get(branch.parent_branch_id) ?? [];
    childIds.push(branch.branch_id);
    children.set(branch.parent_branch_id, childIds);
  }
  const direct = new Map<string, Record<UtilityKey, boolean>>();
  for (const branch of bundle.branches) {
    const outcomes = observationOutcomes.get(branch.branch_id) ?? new Set<string>();
    direct.set(branch.branch_id, Object.fromEntries(
      utilityKeys.map((key) => [key, [...outcomes].some((outcome) => positiveOutcomes[key].has(outcome))]),
    ) as Record<UtilityKey, boolean>);
  }
  const isSoundClosure = (branch: SearchTrainingBundle["branches"][number]) =>
    (branch.state === "blocked" || branch.state === "pruned_sound")
    && branch.evidence_coverage === "soundly_blocked"
    && branch.coverage.children_status === "soundly_closed"
    && soundReasons.has(branch.coverage.completeness_reason)
    && !["", "none", "other"].includes(branch.coverage.soundness_proof_class);
  type Derived = { utility: DerivedUtility; complete: boolean; positiveCount: number };
  const memo = new Map<string, Derived>();
  const visiting = new Set<string>();
  const visit = (branchId: string): Derived => {
    const prior = memo.get(branchId);
    if (prior) return prior;
    if (visiting.has(branchId)) throw new Error("branch lineage contains a cycle");
    visiting.add(branchId);
    const branch = branches.get(branchId);
    if (!branch) throw new Error("branch lineage references an unknown branch");
    const childIds = children.get(branchId) ?? [];
    const childResults = childIds.map(visit);
    const coverage = branch.coverage;
    const complete = isSoundClosure(branch) || (childIds.length > 0
      ? coverage.children_status === "exhaustive"
        && coverage.emitted_child_count === childIds.length
        && coverage.expected_child_count === childIds.length
        && childResults.every((child) => child.complete)
      : (coverage.children_status === "not_applicable" || coverage.children_status === "exhaustive")
        && coverage.emitted_child_count === 0
        && (coverage.expected_child_count === null || coverage.expected_child_count === 0)
        && (branch.evidence_coverage === "complete" || branch.evidence_coverage === "soundly_blocked")
        && (coverage.completeness_reason === "terminal" || coverage.completeness_reason === "not_applicable"
          || soundReasons.has(coverage.completeness_reason)));
    const directUtility = direct.get(branchId)!;
    const utility = Object.fromEntries(utilityKeys.map((key) => {
      const positive = directUtility[key] || childResults.some((child) => child.utility[key] === true);
      return [key, positive ? true : complete ? false : null];
    })) as DerivedUtility;
    const outcomes = observationOutcomes.get(branchId) ?? new Set<string>();
    const directlyUseful = directUtility.physically_material || directUtility.retained
      || directUtility.promoted || (directUtility.proof_valid && directUtility.distinct_realization
        && ![...outcomes].some((outcome) => terminalNegativeOutcomes.has(outcome)));
    const positiveCount = Number(directlyUseful) + childResults.reduce((sum, child) => sum + child.positiveCount, 0);
    const result = { utility, complete, positiveCount };
    visiting.delete(branchId);
    memo.set(branchId, result);
    return result;
  };
  for (const search of bundle.searches) {
    let rootResult: Derived;
    try {
      rootResult = visit(search.root_branch_id);
    } catch (error) {
      return error instanceof Error ? error.message : "invalid branch lineage";
    }
    const reachable = new Set<string>();
    const pending = [search.root_branch_id];
    while (pending.length > 0) {
      const branchId = pending.pop()!;
      if (reachable.has(branchId)) continue;
      reachable.add(branchId);
      pending.push(...(children.get(branchId) ?? []));
    }
    const owned = bundle.branches.filter((branch) => branch.search_id === search.search_id).map((branch) => branch.branch_id);
    if (owned.some((branchId) => !reachable.has(branchId)) || reachable.size !== owned.length) return "search contains disconnected branches";
    if ((search.coverage === "complete" || search.coverage === "soundly_pruned")
      && rootResult.utility.proof_valid === null) return "complete search has unknown descendant utility";
    if (search.fragment.kind === "full_trace" && search.fragment.external_parent_branch_id !== null) {
      return "full search trace cannot have an external parent";
    }
  }
  for (const branch of bundle.branches) {
    const directUtility = direct.get(branch.branch_id)!;
    const derived = memo.get(branch.branch_id)!;
    const useful = derived.positiveCount > 0 ? true : derived.complete ? false : null;
    for (const key of utilityKeys) {
      if (branch.direct_utility[key] !== directUtility[key]) return "noncanonical direct utility label";
      if (branch.descendant_utility[key] !== derived.utility[key]) return "noncanonical descendant utility label";
    }
    if (branch.descendant_utility.useful !== useful) return "noncanonical useful-descendant label";
    let expectedClass: typeof branch.survival.class = "KEEP_UNCERTAIN";
    let expectedAuthority: typeof branch.survival.authority = "incomplete_tree";
    if (branch.baseline) {
      expectedClass = "KEEP"; expectedAuthority = "baseline_guard";
    } else if (useful === true) {
      expectedClass = "KEEP"; expectedAuthority = "observed_positive_path";
    } else if (isSoundClosure(branch)) {
      expectedClass = "BLOCKED_BY_CONTRACT"; expectedAuthority = "sound_contract";
    } else if (derived.complete) {
      expectedClass = "PRUNE_HIGH_CONFIDENCE"; expectedAuthority = "derived_complete_tree";
    }
    if (branch.survival.class !== expectedClass || branch.survival.authority !== expectedAuthority
      || branch.survival.positive_descendant_count !== derived.positiveCount) return "noncanonical survival label";
  }
  return null;
}

http.route({
  path: "/api/health",
  method: "GET",
  handler: httpAction(async () => jsonResponse({
    status: "ok",
    service: "vladder-contributions-v1",
    review_schema: "vladder-agent-review-v1",
    training_schema: "vladder-model-training-bundle-v3",
    model_training_schema: "vladder-model-training-bundle-v3",
    legacy_training_submission: "retired_410",
    public_submission: false,
    capability_submission: true,
    public_capability_registration: true,
    moderation: "pending_by_default",
  })),
});

http.route({
  path: "/api/contributors/register",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const input = await readBoundedJson(request);
    if (input instanceof Response) return input;
    const body = input.value;
    if (typeof body !== "object" || body === null) return jsonResponse({ error: "invalid registration" }, 400);
    const scope = (body as { scope?: unknown }).scope;
    const clientVersion = (body as { client_version?: unknown }).client_version;
    if (scope !== "review:write" && scope !== "training:write") {
      return jsonResponse({ error: "scope must be review:write or training:write" }, 400);
    }
    if (typeof clientVersion !== "string" || clientVersion.length < 1 || clientVersion.length > 80) {
      return jsonResponse({ error: "client_version must contain 1 to 80 characters" }, 400);
    }
    try {
      const limit = await consumePublicLimit(ctx, request, "credential");
      if (!limit.allowed) return jsonResponse({ error: "daily capability registration limit exceeded" }, 429);
      const token = randomCapability();
      const credentialId = `credential:${crypto.randomUUID()}`;
      await ctx.runMutation(internal.contributors.issue, {
        credentialId,
        tokenHash: await sha256(token),
        scope,
        clientVersion,
      });
      return jsonResponse({
        schema_version: "vladder-contributor-capability-v1",
        credential_id: credentialId,
        scope,
        token,
      }, 201);
    } catch (error) {
      const message = error instanceof Error ? error.message : "registration failed";
      return jsonResponse({ error: message.slice(0, 1000) }, message.includes("not configured") ? 503 : 400);
    }
  }),
});

http.route({
  path: "/api/reviews",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const credential = await authorizeSubmission(ctx, request, "review:write");
    if (!credential.allowed) {
      return jsonResponse({ error: credential.reason }, credential.reason === "scope_denied" ? 403 : 401);
    }
    const input = await readBoundedJson(request);
    if (input instanceof Response) return input;
    const review = input.value as AgentReview;
    const validateOnly = new URL(request.url).searchParams.get("validate_only") === "true";
    const payloadHash = await sha256(input.text);
    try {
      await ctx.runMutation(internal.reviews.storeReview, { review, payloadHash, validateOnly: true });
      const boundsError = reviewBounds(review);
      if (boundsError) return jsonResponse({ error: boundsError }, 400);
      if (validateOnly) return jsonResponse({ status: "valid", stored: false, schema_version: "vladder-agent-review-v1" });
      if (!credential.trusted) {
        const limit = await consumePublicLimit(ctx, request, "review", credential.rateLimitIdentity);
        if (!limit.allowed) return jsonResponse({ error: "daily capability review limit exceeded" }, 429);
      }
      const result = await ctx.runMutation(internal.reviews.storeReview, { review, payloadHash, validateOnly: false });
      return jsonResponse({ status: "accepted_for_moderation", ...result }, result.duplicate ? 200 : 202);
    } catch (error) {
      const message = error instanceof Error ? error.message : "invalid review";
      return jsonResponse({ error: message.slice(0, 1000) }, message.includes("not configured") ? 503 : 400);
    }
  }),
});

http.route({
  path: "/api/training",
  method: "POST",
  handler: httpAction(async () => jsonResponse({
    error: "legacy training submission is retired; upgrade vLadder and submit vladder-model-training-bundle-v3 to /api/training/v3",
    required_schema: "vladder-model-training-bundle-v3",
    endpoint: "/api/training/v3",
  }, 410)),
});

http.route({
  path: "/api/training/v2",
  method: "POST",
  handler: httpAction(async () => jsonResponse({
    error: "flat v2 training submission is retired; submit lineage-aware v3 data",
    required_schema: "vladder-model-training-bundle-v3",
    endpoint: "/api/training/v3",
  }, 410)),
});

http.route({
  path: "/api/training/v3",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const credential = await authorizeSubmission(ctx, request, "training:write");
    if (!credential.allowed) {
      return jsonResponse({ error: credential.reason }, credential.reason === "scope_denied" ? 403 : 401);
    }
    const input = await readBoundedJson(request);
    if (input instanceof Response) return input;
    const bundle = input.value as SearchTrainingBundle;
    const validateOnly = new URL(request.url).searchParams.get("validate_only") === "true";
    const payloadHash = await sha256(input.text);
    try {
      await ctx.runMutation(internal.searchTraining.storeBundle, { bundle, payloadHash, validateOnly: true });
      const boundsError = searchTrainingBounds(bundle);
      if (boundsError) return jsonResponse({ error: boundsError }, 400);
      if (validateOnly) return jsonResponse({ status: "valid", stored: false, schema_version: "vladder-model-training-bundle-v3" });
      if (!credential.trusted) {
        const limit = await consumePublicLimit(ctx, request, "training", credential.rateLimitIdentity);
        if (!limit.allowed) return jsonResponse({ error: "daily capability training limit exceeded" }, 429);
      }
      const result = await ctx.runMutation(internal.searchTraining.storeBundle, { bundle, payloadHash, validateOnly: false });
      return jsonResponse({ status: "accepted_for_moderation", ...result }, result.duplicate ? 200 : 202);
    } catch (error) {
      const message = error instanceof Error ? error.message : "invalid model-training bundle";
      return jsonResponse({ error: message.slice(0, 1000) }, 400);
    }
  }),
});

http.route({
  path: "/api/reviews/approval",
  method: "PATCH",
  handler: httpAction(async (ctx, request) => {
    const expected = process.env.VLADDER_REVIEW_ADMIN_TOKEN;
    if (!expected || request.headers.get("authorization") !== `Bearer ${expected}`) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }
    const body = await request.json();
    if (typeof body !== "object" || body === null || typeof body.reviewId !== "string" || typeof body.approved !== "boolean") {
      return jsonResponse({ error: "reviewId and approved are required" }, 400);
    }
    await ctx.runMutation(internal.reviews.setApproval, { reviewId: body.reviewId, approved: body.approved });
    return jsonResponse({ status: "updated" });
  }),
});

http.route({
  path: "/api/training/approval",
  method: "PATCH",
  handler: httpAction(async (ctx, request) => {
    const expected = process.env.VLADDER_REVIEW_ADMIN_TOKEN;
    if (!expected || request.headers.get("authorization") !== `Bearer ${expected}`) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }
    const body = await request.json();
    if (typeof body !== "object" || body === null || typeof body.submissionId !== "string" || typeof body.approved !== "boolean") {
      return jsonResponse({ error: "submissionId and approved are required" }, 400);
    }
    await ctx.runMutation(internal.training.setApproval, { submissionId: body.submissionId, approved: body.approved });
    return jsonResponse({ status: "updated" });
  }),
});

http.route({
  path: "/api/training/v2/approval",
  method: "PATCH",
  handler: httpAction(async (ctx, request) => {
    const expected = process.env.VLADDER_REVIEW_ADMIN_TOKEN;
    if (!expected || request.headers.get("authorization") !== `Bearer ${expected}`) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }
    const body = await request.json();
    if (typeof body !== "object" || body === null || typeof body.submissionId !== "string" || typeof body.approved !== "boolean") {
      return jsonResponse({ error: "submissionId and approved are required" }, 400);
    }
    await ctx.runMutation(internal.modelTraining.setApproval, {
      submissionId: body.submissionId,
      approved: body.approved,
    });
    return jsonResponse({ status: "updated" });
  }),
});

http.route({
  path: "/api/training/v3/approval",
  method: "PATCH",
  handler: httpAction(async (ctx, request) => {
    const expected = process.env.VLADDER_REVIEW_ADMIN_TOKEN;
    if (!expected || request.headers.get("authorization") !== `Bearer ${expected}`) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }
    const body = await request.json();
    if (typeof body !== "object" || body === null || typeof body.submissionId !== "string" || typeof body.approved !== "boolean") {
      return jsonResponse({ error: "submissionId and approved are required" }, 400);
    }
    await ctx.runMutation(internal.searchTraining.setApproval, {
      submissionId: body.submissionId,
      approved: body.approved,
    });
    return jsonResponse({ status: "updated" });
  }),
});

http.route({
  path: "/api/contributors/revoke",
  method: "PATCH",
  handler: httpAction(async (ctx, request) => {
    const expected = process.env.VLADDER_REVIEW_ADMIN_TOKEN;
    if (!expected || request.headers.get("authorization") !== `Bearer ${expected}`) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }
    const body = await request.json();
    if (typeof body !== "object" || body === null || typeof body.credentialId !== "string") {
      return jsonResponse({ error: "credentialId is required" }, 400);
    }
    const revoked = await ctx.runMutation(internal.contributors.revoke, { credentialId: body.credentialId });
    return jsonResponse({ status: revoked ? "revoked" : "not_found" }, revoked ? 200 : 404);
  }),
});

http.route({
  path: "/api/reviews",
  method: "GET",
  handler: httpAction(async (ctx, request) => {
    const url = new URL(request.url);
    const rawLimit = Number(url.searchParams.get("limit") ?? "12");
    const limit = Number.isFinite(rawLimit) ? rawLimit : 12;
    const reviews = await ctx.runQuery(api.reviews.listApproved, { limit });
    return jsonResponse({ schema_version: "vladder-approved-reviews-v1", reviews });
  }),
});

export default http;
