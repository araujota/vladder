import { v } from "convex/values";
import { internalMutation } from "./_generated/server";

const capabilityScope = v.union(v.literal("review:write"), v.literal("training:write"));

export const issue = internalMutation({
  args: {
    credentialId: v.string(),
    tokenHash: v.string(),
    scope: capabilityScope,
    clientVersion: v.string(),
  },
  returns: v.null(),
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("contributorCapabilities")
      .withIndex("by_token_hash", (q) => q.eq("tokenHash", args.tokenHash))
      .unique();
    if (existing !== null) throw new Error("capability token collision");
    await ctx.db.insert("contributorCapabilities", {
      ...args,
      createdAt: Date.now(),
      lastUsedAt: null,
      revoked: false,
    });
    return null;
  },
});

export const authorize = internalMutation({
  args: { tokenHash: v.string(), requiredScope: capabilityScope },
  returns: v.object({ allowed: v.boolean(), reason: v.string() }),
  handler: async (ctx, args) => {
    const credential = await ctx.db
      .query("contributorCapabilities")
      .withIndex("by_token_hash", (q) => q.eq("tokenHash", args.tokenHash))
      .unique();
    if (credential === null) return { allowed: false, reason: "unknown_credential" };
    if (credential.revoked) return { allowed: false, reason: "revoked_credential" };
    if (credential.scope !== args.requiredScope) return { allowed: false, reason: "scope_denied" };
    await ctx.db.patch(credential._id, { lastUsedAt: Date.now() });
    return { allowed: true, reason: "authorized" };
  },
});

export const revoke = internalMutation({
  args: { credentialId: v.string() },
  returns: v.boolean(),
  handler: async (ctx, args) => {
    const credential = await ctx.db
      .query("contributorCapabilities")
      .withIndex("by_credential_id", (q) => q.eq("credentialId", args.credentialId))
      .unique();
    if (credential === null) return false;
    await ctx.db.patch(credential._id, { revoked: true });
    return true;
  },
});
