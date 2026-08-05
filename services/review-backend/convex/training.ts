import { v } from "convex/values";
import { internalMutation } from "./_generated/server";
import { trainingBundleValidator } from "./trainingValidators";

export const storeBundle = internalMutation({
  args: {
    bundle: trainingBundleValidator,
    payloadHash: v.string(),
    validateOnly: v.boolean(),
  },
  returns: v.object({ id: v.union(v.id("trainingSubmissions"), v.null()), duplicate: v.boolean(), stored: v.boolean() }),
  handler: async (ctx, args) => {
    if (args.validateOnly) {
      return { id: null, duplicate: false, stored: false };
    }
    const existing = await ctx.db
      .query("trainingSubmissions")
      .withIndex("by_bundle_id", (q) => q.eq("bundleId", args.bundle.bundle_id))
      .unique();
    if (existing !== null) {
      if (existing.payloadHash !== args.payloadHash) {
        throw new Error("bundle ID already exists with a different payload hash");
      }
      return { id: existing._id, duplicate: true, stored: true };
    }
    const id = await ctx.db.insert("trainingSubmissions", {
      bundleId: args.bundle.bundle_id,
      releaseVersion: args.bundle.vladder_version,
      projectId: args.bundle.dataset.project_id,
      grammarVersion: args.bundle.dataset.grammar_version,
      approved: false,
      submittedAt: Date.now(),
      payloadHash: args.payloadHash,
      bundle: args.bundle,
    });
    return { id, duplicate: false, stored: true };
  },
});

export const setApproval = internalMutation({
  args: { submissionId: v.id("trainingSubmissions"), approved: v.boolean() },
  returns: v.null(),
  handler: async (ctx, args) => {
    await ctx.db.patch(args.submissionId, { approved: args.approved });
    return null;
  },
});
