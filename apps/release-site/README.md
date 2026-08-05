# vLadder Release Site

The site is static-first and remains usable without the review backend.

```bash
npm install
npm run check
npm run build
npm run check:links
```

Set `NEXT_PUBLIC_REVIEW_LIST_URL` to the Convex HTTP action URL to show approved reviews. Downloads
always resolve through the public GitHub releases page.

The authenticated production project is `araujota97gmailcoms-projects/vladder-release`, published
at <https://vladder-release.vercel.app>. Vercel project IDs and OIDC credentials remain in ignored
local files.
