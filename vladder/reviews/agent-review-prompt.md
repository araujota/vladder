# Canonical vLadder Agent Review Prompt v1

Review this vLadder investigation from the evidence bundle, not from the proposed rewrite alone.
Return exactly one JSON object conforming to `vladder-agent-review-v1`.

Required method:

1. Identify the selected source/build/workload boundary and whether coverage was meaningful.
2. State what candidate was generated, what exact proof class closed, and every excluded claim.
3. State whether paired physical evidence was collected and whether the effect interval cleared the
   predeclared threshold.
4. Separate local-region, composed-system, and retained-production results.
5. List materially rejected candidates and why they were rejected.
6. List unresolved ownership, lifetime, protocol, external-system, numerical, or workload bounds.
7. Give one bounded claim that the evidence supports. Do not infer whole-program equivalence from
   a local proof and do not infer production value from a microbenchmark.
8. Recommend next work only when it follows from attribution or a named proof/coverage gap.

Privacy constraints:

- Do not include source code, raw proof artifacts, credentials, prompts, personal data, or arbitrary
  attachments.
- Identify evidence by hashes, schema versions, classifications, and concise summaries.
- Set `privacy.source_included` and `privacy.raw_artifacts_included` to `false`.
- Set `privacy.submission_consent` to `true` only when the user explicitly approved submission.

Outcome meanings:

- `retained_win`: proved, physically promoted, integrated, and retained.
- `verified_negative`: complete measured search whose accepted candidates did not win.
- `partial_evidence`: useful capture/proof/measurement exists but promotion is incomplete.
- `workflow_failure`: the intended evidence chain failed before a defensible result.
- `revalidation`: previously retained evidence was rerun without a new optimization claim.
