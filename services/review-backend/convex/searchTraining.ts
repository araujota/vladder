import { v } from "convex/values";
import { internalMutation } from "./_generated/server";
import { searchTrainingBundleValidator } from "./searchTrainingValidators";

export const storeBundle = internalMutation({
  args: { bundle: searchTrainingBundleValidator, payloadHash: v.string(), validateOnly: v.boolean() },
  returns: v.object({
    id: v.union(v.id("searchTrainingSubmissions"), v.null()), duplicate: v.boolean(), stored: v.boolean(),
  }),
  handler: async (ctx, args) => {
    if (args.validateOnly) return { id: null, duplicate: false, stored: false };
    const existing = await ctx.db
      .query("searchTrainingSubmissions")
      .withIndex("by_bundle_id", (q) => q.eq("bundleId", args.bundle.bundle_id))
      .unique();
    if (existing !== null) {
      if (existing.payloadHash !== args.payloadHash) throw new Error("search-training bundle ID conflicts with stored payload");
      return { id: existing._id, duplicate: true, stored: true };
    }
    const id = await ctx.db.insert("searchTrainingSubmissions", {
      bundleId: args.bundle.bundle_id, releaseVersion: args.bundle.vladder_version,
      identityEpoch: args.bundle.dataset.identity_epoch,
      rootIds: args.bundle.roots.map((root) => root.root_id),
      searchIds: args.bundle.searches.map((search) => search.search_id),
      approved: false, submittedAt: Date.now(), payloadHash: args.payloadHash, bundle: args.bundle,
    });
    return { id, duplicate: false, stored: true };
  },
});

export const setApproval = internalMutation({
  args: { submissionId: v.id("searchTrainingSubmissions"), approved: v.boolean() },
  returns: v.null(),
  handler: async (ctx, args) => {
    await ctx.db.patch(args.submissionId, { approved: args.approved });
    return null;
  },
});
