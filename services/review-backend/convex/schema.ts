import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";
import { agentReviewValidator } from "./reviewValidators";
import { trainingBundleValidator } from "./trainingValidators";
import { modelTrainingBundleValidator } from "./modelTrainingValidators";
import { searchTrainingBundleValidator } from "./searchTrainingValidators";

export default defineSchema({
  reviews: defineTable({
    reviewId: v.string(),
    releaseVersion: v.string(),
    projectName: v.string(),
    disposition: v.string(),
    approved: v.boolean(),
    submittedAt: v.number(),
    payloadHash: v.string(),
    review: agentReviewValidator,
  })
    .index("by_review_id", ["reviewId"])
    .index("by_approved_and_submitted_at", ["approved", "submittedAt"])
    .index("by_project_name_and_submitted_at", ["projectName", "submittedAt"])
    .index("by_release_version_and_submitted_at", ["releaseVersion", "submittedAt"]),
  mlBundles: defineTable({
    bundleId: v.string(),
    schemaVersion: v.string(),
    reviewId: v.optional(v.id("reviews")),
    storageId: v.id("_storage"),
    sha256: v.string(),
    byteCount: v.number(),
    consentScope: v.string(),
    approved: v.boolean(),
    createdAt: v.number(),
  })
    .index("by_bundle_id", ["bundleId"])
    .index("by_approved_and_created_at", ["approved", "createdAt"]),
  trainingSubmissions: defineTable({
    bundleId: v.string(),
    releaseVersion: v.string(),
    projectId: v.string(),
    grammarVersion: v.string(),
    approved: v.boolean(),
    submittedAt: v.number(),
    payloadHash: v.string(),
    bundle: trainingBundleValidator,
  })
    .index("by_bundle_id", ["bundleId"])
    .index("by_approved_and_submitted_at", ["approved", "submittedAt"])
    .index("by_project_id_and_submitted_at", ["projectId", "submittedAt"]),
  modelTrainingSubmissions: defineTable({
    bundleId: v.string(),
    releaseVersion: v.string(),
    identityEpoch: v.string(),
    rootIds: v.array(v.string()),
    approved: v.boolean(),
    submittedAt: v.number(),
    payloadHash: v.string(),
    bundle: modelTrainingBundleValidator,
  })
    .index("by_bundle_id", ["bundleId"])
    .index("by_approved_and_submitted_at", ["approved", "submittedAt"])
    .index("by_identity_epoch_and_submitted_at", ["identityEpoch", "submittedAt"]),
  searchTrainingSubmissions: defineTable({
    bundleId: v.string(),
    releaseVersion: v.string(),
    identityEpoch: v.string(),
    rootIds: v.array(v.string()),
    searchIds: v.array(v.string()),
    approved: v.boolean(),
    submittedAt: v.number(),
    payloadHash: v.string(),
    bundle: searchTrainingBundleValidator,
  })
    .index("by_bundle_id", ["bundleId"])
    .index("by_approved_and_submitted_at", ["approved", "submittedAt"])
    .index("by_identity_epoch_and_submitted_at", ["identityEpoch", "submittedAt"]),
  contributorCapabilities: defineTable({
    credentialId: v.string(),
    tokenHash: v.string(),
    scope: v.union(v.literal("review:write"), v.literal("training:write")),
    clientVersion: v.string(),
    createdAt: v.number(),
    lastUsedAt: v.union(v.number(), v.null()),
    revoked: v.boolean(),
  })
    .index("by_token_hash", ["tokenHash"])
    .index("by_credential_id", ["credentialId"]),
  submissionRateLimits: defineTable({
    fingerprintHash: v.string(),
    bucket: v.string(),
    kind: v.union(v.literal("review"), v.literal("training"), v.literal("credential")),
    count: v.number(),
    updatedAt: v.number(),
  }).index("by_fingerprint_hash_and_bucket_and_kind", ["fingerprintHash", "bucket", "kind"]),
});
