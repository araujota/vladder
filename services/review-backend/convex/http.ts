import { httpRouter } from "convex/server";
import type { Infer } from "convex/values";
import { httpAction } from "./_generated/server";
import { api, internal } from "./_generated/api";
import { agentReviewValidator } from "./reviewValidators";
import { trainingBundleValidator } from "./trainingValidators";

type AgentReview = Infer<typeof agentReviewValidator>;
type TrainingBundle = Infer<typeof trainingBundleValidator>;
type SubmissionKind = "review" | "training" | "credential";
type CapabilityScope = "review:write" | "training:write";

const MAX_PAYLOAD_BYTES = 128 * 1024;
const DAILY_LIMITS: Record<SubmissionKind, number> = { review: 20, training: 10_000, credential: 10 };
const HASH_PATTERN = /^[a-f0-9]{64}$/;

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
    return jsonResponse({ error: "payload exceeds 128 KiB" }, 413);
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

function trainingBounds(bundle: TrainingBundle): string | null {
  if (bundle.examples.length < 1 || bundle.examples.length > 256) return "examples must contain 1 to 256 records";
  if (!HASH_PATTERN.test(bundle.dataset.grammar_hash) || !HASH_PATTERN.test(bundle.dataset.hardware_manifest_hash)) {
    return "invalid dataset hash";
  }
  const ids = new Set<string>();
  for (const example of bundle.examples) {
    if (ids.has(example.example_id)) return "duplicate example_id";
    ids.add(example.example_id);
    if (!HASH_PATTERN.test(example.semantic_root_hash) || !HASH_PATTERN.test(example.candidate_hash)) {
      return "invalid example hash";
    }
    if (example.numeric_features.length > 256 || example.categorical_features.length > 128) {
      return "example feature count exceeds schema bounds";
    }
    if (!Number.isInteger(example.evidence.sample_count) || example.evidence.sample_count < 0) {
      return "sample_count must be a nonnegative integer";
    }
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
    training_schema: "vladder-training-bundle-v1",
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
  handler: httpAction(async (ctx, request) => {
    const credential = await authorizeSubmission(ctx, request, "training:write");
    if (!credential.allowed) {
      return jsonResponse({ error: credential.reason }, credential.reason === "scope_denied" ? 403 : 401);
    }
    const input = await readBoundedJson(request);
    if (input instanceof Response) return input;
    const bundle = input.value as TrainingBundle;
    const validateOnly = new URL(request.url).searchParams.get("validate_only") === "true";
    const payloadHash = await sha256(input.text);
    try {
      await ctx.runMutation(internal.training.storeBundle, { bundle, payloadHash, validateOnly: true });
      const boundsError = trainingBounds(bundle);
      if (boundsError) return jsonResponse({ error: boundsError }, 400);
      if (validateOnly) return jsonResponse({ status: "valid", stored: false, schema_version: "vladder-training-bundle-v1" });
      if (!credential.trusted) {
        const limit = await consumePublicLimit(ctx, request, "training", credential.rateLimitIdentity);
        if (!limit.allowed) return jsonResponse({ error: "daily capability training limit exceeded" }, 429);
      }
      const result = await ctx.runMutation(internal.training.storeBundle, { bundle, payloadHash, validateOnly: false });
      return jsonResponse({ status: "accepted_for_moderation", ...result }, result.duplicate ? 200 : 202);
    } catch (error) {
      const message = error instanceof Error ? error.message : "invalid training bundle";
      return jsonResponse({ error: message.slice(0, 1000) }, message.includes("not configured") ? 503 : 400);
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
