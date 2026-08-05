import { v } from "convex/values";
import { internalMutation } from "./_generated/server";

export const consume = internalMutation({
  args: {
    fingerprintHash: v.string(),
    bucket: v.string(),
    kind: v.union(v.literal("review"), v.literal("training")),
    limit: v.number(),
  },
  returns: v.object({ allowed: v.boolean(), remaining: v.number() }),
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("submissionRateLimits")
      .withIndex("by_fingerprint_hash_and_bucket_and_kind", (q) =>
        q.eq("fingerprintHash", args.fingerprintHash).eq("bucket", args.bucket).eq("kind", args.kind),
      )
      .unique();
    if (existing !== null && existing.count >= args.limit) {
      return { allowed: false, remaining: 0 };
    }
    const count = (existing?.count ?? 0) + 1;
    if (existing === null) {
      await ctx.db.insert("submissionRateLimits", {
        fingerprintHash: args.fingerprintHash,
        bucket: args.bucket,
        kind: args.kind,
        count,
        updatedAt: Date.now(),
      });
    } else {
      await ctx.db.patch(existing._id, { count, updatedAt: Date.now() });
    }
    return { allowed: true, remaining: Math.max(0, args.limit - count) };
  },
});
