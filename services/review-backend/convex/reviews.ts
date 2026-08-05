import { v } from "convex/values";
import { internalMutation, query } from "./_generated/server";
import { agentReviewValidator } from "./reviewValidators";

export const listApproved = query({
  args: { limit: v.optional(v.number()) },
  returns: v.array(agentReviewValidator),
  handler: async (ctx, args) => {
    const limit = Math.max(1, Math.min(50, Math.trunc(args.limit ?? 12)));
    const rows = await ctx.db
      .query("reviews")
      .withIndex("by_approved_and_submitted_at", (q) => q.eq("approved", true))
      .order("desc")
      .take(limit);
    return rows.map((row) => row.review);
  },
});

export const storeReview = internalMutation({
  args: { review: agentReviewValidator, payloadHash: v.string(), validateOnly: v.boolean() },
  returns: v.object({ id: v.union(v.id("reviews"), v.null()), duplicate: v.boolean(), stored: v.boolean() }),
  handler: async (ctx, args) => {
    if (args.validateOnly) {
      return { id: null, duplicate: false, stored: false };
    }
    const existing = await ctx.db
      .query("reviews")
      .withIndex("by_review_id", (q) => q.eq("reviewId", args.review.review_id))
      .unique();
    if (existing !== null) {
      if (existing.payloadHash !== args.payloadHash) {
        throw new Error("review ID already exists with a different payload hash");
      }
      return { id: existing._id, duplicate: true, stored: true };
    }
    const id = await ctx.db.insert("reviews", {
      reviewId: args.review.review_id,
      releaseVersion: args.review.vladder_version,
      projectName: args.review.project.name,
      disposition: args.review.assessment.outcome,
      approved: false,
      submittedAt: Date.now(),
      payloadHash: args.payloadHash,
      review: args.review,
    });
    return { id, duplicate: false, stored: true };
  },
});

export const setApproval = internalMutation({
  args: { reviewId: v.id("reviews"), approved: v.boolean() },
  returns: v.null(),
  handler: async (ctx, args) => {
    await ctx.db.patch(args.reviewId, { approved: args.approved });
    return null;
  },
});
