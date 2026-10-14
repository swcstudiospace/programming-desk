---
name: spectrumwebco-marketing
description: Layout, build, test, and deploy rules for the Spectrum Web Co marketing site (Next.js, Convex in Sydney, Tavus meetings, Supabase auth). Use before editing swcstudiospace/spectrumwebco-marketing or promoting www.spectrumweb.co.
bots: [bot-02-web-edge, bot-00-programming-lead]
gates: [G-3, G-5]
---

# Spectrum Web Co marketing site

## L1 — Summary

The public site is a **Next.js 16 App Router** app (anime.js, three.js) deployed on **Vercel** at `https://www.spectrumweb.co`. Meetings and the Tavus PAL run on **Convex in Sydney** (`ap-southeast-2`). Sign-in stays on **Supabase** in the ClippyOS project, with `site_` tables. The old Postgres meeting dispatcher is retired.

**Every production deploy needs Ming's explicit yes in the ticket.** A preview build, a local `npx convex dev`, and reading the dashboard are not that yes. `npx convex deploy`, a Vercel production promotion, and `npm run convex:env -- --prod` are deploys. Stop and ask when the yes is missing.

```
About to change the site?
├─▶ Read the pin in §0. Do not invent a GenUI module or a v2.2 changelog. §0
│
├─▶ Local loop: npm install && npm run dev. Prove with npm test and npm run lint. §2
│
├─▶ Convex or Tavus? Keys are per deployment. Production key ≠ preview key. §3
│
├─▶ Auth or email? Supabase dashboard plus the Next hooks. Do not add a Google callback route. §4
│
└─▶ Deploy? Ming's yes first, then the Vercel build in §5. Roll back the deployment, not the data.
```

**A `NEXT_PUBLIC_` value is public** the moment the page is served. The production client bundle inlines the Convex URL. Do not put `SITE_SERVER_SECRET`, `TAVUS_API_KEY`, `RESEND_API_KEY`, Google client secrets, or hook secrets in client code or in this skill.

---

## L2 — Method

### §0 What this skill was able to read

The ticket names commit `e0b71bd` on branch `gsd/product-example-plans` (pull request 35) as the pin. Cloning `swcstudiospace/spectrumwebco-marketing` from this seat returned **404**. That commit's git log was not read.

Facts below come from the desk docs-plane chunks of the ingested repo (`README.md`, `CONVEX-SETUP.md`, `MEETINGS-SETUP.md`, `AUTH-SETUP.md`, `DASHBOARD-NOTE.md`, `GMAIL-SETUP.md`) and from the live Vercel site's client bundle, which constructs `ConvexReactClient` against an `ap-southeast-2.convex.cloud` deployment.

These strings were **not** in those chunks or in the home and docs HTML: a module named GenUI, an overlay component, or a version label `v2.2`. Do not add a GenUI overlay, and do not write a v2.2 launch note, until that commit is opened and the file is in the diff. The live site on Vercel is the production surface; it is not by itself proof of what pull request 35 contains.

### §1 Layout

| Path | What it is |
|---|---|
| `app/` | App Router pages, `globals.css`, `cyber.css` (neon layer on top of the globals) |
| `app/auth/callback`, `confirm`, `signout` | Supabase auth routes. There is no `/api/auth/google/callback` |
| `app/book`, `/api/meetings` | Booking form. Next validates, then calls Convex `meetings:book` |
| `/api/tavus/webhook` | Transcript and structured recap from Tavus |
| `/api/auth/email-hook`, `/api/auth/sms-hook` | Supabase Send Email / Send SMS hooks |
| `components/ConvexProvider.tsx` | Client Convex provider. Falls back from the public URL |
| `components/auth/SignIn.tsx` | Google, X, magic link, phone OTP, Solana and Ethereum wallets |
| `lib/convex/server.ts` | Server Convex client. Prefers `CONVEX_URL`, else `NEXT_PUBLIC_CONVEX_URL` |
| `lib/auth-methods.ts` | Reads Supabase auth settings and greys out methods that are off |
| `lib/content.ts`, `lib/seo.ts` | Page copy and `pageMetadata()` |
| `lib/rigs/`, `lib/motion/live.ts` | three.js rigs and anime.js pointer interaction |
| `convex/` | Meetings actions, `meetings:sweep` cron, `convex/lib/tavus.ts` |
| `scripts/build.mjs` | Vercel build. Deploys Convex functions only when the deploy key is set |
| `scripts/tavus-pal.mjs` | Creates or updates Aimee's PAL. PAL Maker edits are overwritten on the next run |
| `scripts/render-emails.tsx` | Renders `emails/` and regenerates `supabase/templates/` |
| `emails/`, `supabase/templates/` | React Email sources and the dashboard HTML fallbacks |
| `content/blog/` | Long-form pages |

Home, services, products, and the four product pages each have a named 3D rig (`engine`, `hub`, `launch`, `sorter`, `mast`, `carousel`, `kanban`, `reels`, `stadium`, `circuit`). Social Narratives is drawn as a planned wireframe, not a bookable flow.

### §2 Build and test

```bash
npm install
npm run dev          # http://localhost:3000
npm run lint
npm test             # meetings and the rest of the repo suite
npm run build && npm start
npx tsx scripts/render-emails.tsx   # writes emails-preview/ and refreshes supabase/templates/
```

`npx convex dev` is the local function sync. It creates `convex/_generated/` and prompts for a deployment name. Keep the defaults unless the ticket names a different deployment.

`npm run convex:env -- .env.meetings` pushes the meetings env file into the **dev** Convex deployment. `--prod` targets production and is a deploy (§5).

A green `npm run dev` does not prove the Convex cron, the Tavus webhook, or a Supabase hook. Those need the deployment the ticket names.

### §3 Convex (Sydney) and Tavus PAL

The production client talks to Convex in **Sydney (`ap-southeast-2`)**. Deploy keys are per deployment, not per project. A key minted while the dashboard is on Preview is rejected for Production. Mint the Production key with the environment picker on Production, store it as `CONVEX_DEPLOY_KEY` on the matching Vercel environment, and do the same for Preview with a preview key.

| Variable | Where | Why |
|---|---|---|
| `CONVEX_DEPLOYMENT` | Server | `npx convex deploy` target |
| `NEXT_PUBLIC_CONVEX_URL` | Public | Client provider and server fallback. Inlined into the browser bundle |
| `CONVEX_URL` | Server only | Preferred by `lib/convex/server.ts` |
| `CONVEX_DEPLOY_KEY` | Vercel, matching scope | `scripts/build.mjs` runs `npx convex deploy --cmd "next build"` only when this is set. Without it the build is Next.js only |
| `SITE_SERVER_SECRET` | Convex, Vercel, and the PAL script, identical | Authenticates Next → Convex and the PAL |
| `TAVUS_API_KEY`, `TAVUS_PAL_ID` | Convex, not only Vercel | The join runs inside Convex |
| `TAVUS_FACE_ID` | Convex, optional | Overrides the PAL face for every call |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | Convex | Calendar event and Meet link |
| `SITE_URL` | Convex | Callbacks the PAL and the webhook use |

Booking flow: `/book` → `/api/meetings` → `meetings:book`. Convex stores the row, creates one Calendar event whose id is derived from the meeting id (a retry must not send a second invite), opens the Meet space, and queues Aimee. "Start now" joins immediately. A scheduled call is queued for one minute before start. `meetings:sweep` runs every minute: missed scheduler items, Tavus join retries (4 attempts, at least 30 seconds apart), Calendar retries every 5 minutes up to 12 times. Tavus posts the transcript and recap to `/api/tavus/webhook`. Visitor notes are untrusted text in the briefing.

PAL gotchas:

- A PAL from the previous script has no conferencing username and cannot join Meet. Create a new PAL or update the id, then point `TAVUS_PAL_ID` at it.
- `TAVUS_CONFERENCING_USERNAME` defaults to `spectrumweb-aimee` and must be unique on tavusinvite.com.
- `TAVUS_INVITE_ALLOWLIST` defaults to `ove@spectrumweb.co`.
- `TAVUS_FORCE=1` overwrites unapplied PAL Maker edits. Without it, a PAL with pending Maker changes is left alone. Lasting prompt changes belong in `scripts/tavus-pal.mjs`, because the next run overwrites Maker edits.
- Meeting failures show up on the Convex `meetings` row in `lastError`.

### §4 Supabase consolidation

Auth and the remaining site tables live in the **ClippyOS** Supabase project. Site tables in `public` are prefixed `site_`. Public writes go through `site_*` RPC functions that require `SITE_SERVER_SECRET` (only its SHA-256 is stored in `site_config`).

Meetings **moved off Postgres**. The `pg_cron` job `site-meetings-dispatch` is retired, and `/api/meetings/dispatch` is removed. After a deploy that includes this consolidation, unschedule that cron job. Leaving it scheduled calls a route that is gone.

Sign-in methods already in `SignIn` (do not add a parallel provider route):

- Google and X via `signInWithOAuth`. The Google redirect URI is the Supabase `/auth/v1/callback`, registered on the **same** OAuth client whose id and secret are in Supabase. `Access blocked: This app's request is invalid` means that URI is missing or the consent screen is still in Testing. Publishing the app, or listing the visitor as a tester, is a dashboard step.
- Email magic link and the Send Email hook at `/api/auth/email-hook` (`SEND_EMAIL_HOOK_SECRET`), rendered from `emails/auth/` through Resend. If the hook is off, mail leaves via Supabase's shared sender unless custom SMTP is set (`smtp.resend.com`, port 465, username `resend`).
- Phone OTP via the Send SMS hook at `/api/auth/sms-hook`. While the hook is on, the dashboard SMS template and Twilio fields are ignored. The text says 5 minutes; the provider expiry is 300 seconds and the code length is 6.
- Solana and Ethereum wallets via `signInWithWeb3`. `lib/auth-methods.ts` marks wallet unavailable ("Soon") when settings carry no `web3*` keys. Enable each chain in the dashboard. Redirect URLs need `https://www.spectrumweb.co/**` because the signed message carries the `/login` page URI.

URL configuration: Site URL `https://www.spectrumweb.co`. Redirects include `/auth/callback`, `/auth/confirm`, and the `/**` glob, plus `http://localhost:3000/**` and every preview origin you sign in from. An unlisted origin is rejected because the callback is built from the browser's actual origin.

`authMethods()` also returns every method off when `NEXT_PUBLIC_SUPABASE_URL` or the publishable key is missing, and it falls back to email-only when the settings request fails. A grey "Soon" on Google is not always "provider off".

Members request private-repo access from `/account`. Rows land in `site_repo_requests`. Access is granted in the `swcstudiospace` GitHub organisation, then the row's `status` is set to `granted`.

### §5 Deploy rules

1. Ming has said yes, in the ticket, for this deploy. Record that yes on the receipt under `approvals` when the command is actually run (G-5/G-6). This skill is not that approval.
2. Preview first. Verify the changed pages, the booking path, and sign-in on the preview URL.
3. Production Convex key on the Production Vercel env, preview key on Preview. A mismatch fails the function deploy or ships functions to the wrong deployment.
4. `scripts/build.mjs` is the Vercel build. With `CONVEX_DEPLOY_KEY` it runs `npx convex deploy --cmd "next build"`, so functions, the cron, and the Convex URL ship with the site. Without the key, only Next.js ships and the cron stays on the previous deployment.
5. Rollback is the previous Vercel deployment. It does not unsend a Calendar invite, does not delete a Convex `meetings` row, and does not restore a Supabase cron you already unscheduled. Say which of those the change touched.
6. Do not deploy from a cloud agent, and do not touch the VPS. This repository's desk gates are not the marketing site's pipeline.

### §6 Gotchas

- Preview deploy keys do not deploy Production.
- `SITE_SERVER_SECRET` has to be the same string in Convex, Vercel, and the PAL script run. One of the three drifting fails every authenticated call.
- Booking notes are untrusted. They are fenced in the PAL briefing. Do not concatenate them into a tool call.
- Calendar event id is derived from the meeting id. Changing that derivation double-invites on retry.
- PAL Maker is not the source of truth.
- Do not register `spectrumweb.co/api/auth/google/callback`. That route does not exist.
- Wallet and Google "Soon" states are often dashboard or env, not a code bug (`DASHBOARD-NOTE.md`).
- `npm run convex:env -- --prod` writes production Convex env. Treat it as a deploy.
- Copy `.env.example` to `.env.local`. Never commit either file with values filled in.
