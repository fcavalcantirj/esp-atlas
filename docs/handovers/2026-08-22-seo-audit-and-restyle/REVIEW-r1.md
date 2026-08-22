---
verdict: APPROVED
round: 1
---

# Review r1

Judged only against the acceptance checklist and blocking constraints in `HANDOVER.md`. The builder's re-verification (all `[REAL]` claims re-checked against prod, repo, gh, gcloud and the zip; seven additions, none contradicting) is exactly the pass the ritual asks for — discrepancy 7 (docs-only PRs are un-mergeable under the current `paths:` filter + `enforce_admins`) is a real blocker the author missed, and the metadata-merge finding (root `openGraph`/`twitter` never reach part pages) is correct and useful.

## Checklist verdicts

1. Six constraints restated first, own words, each correct (including `enforce_admins: true`, which the handover did not state): **satisfied**.
2. Exactly the six files copied; `lib/api.ts`, `package.json`/lockfile, ESLint, `vercel-build`, `next.config.ts`, `apps/web/api/**` kept; no zip-only scaffolding; `git status` gate of "exactly six modified": **satisfied**.
3. Verification chain verbatim; 12 screenshots (3 routes × 2 widths × 2 themes) with a verified dark-mode method (`--force-dark-mode` asserted via `--dump-dom`); post-merge prod curls incl. Newsreader woff2 / `.footer-standfirst` checks: **satisfied**.
4. Evidence table names source + method per spec section; limitations stated with the cheapest upgrade path (backlinks, competitors, history): **satisfied**.
5. `docs/seo-audit/2026-08-22.md`, 13 sections in order, bullets answered or `N/A — why`, priority tags, effort-vs-impact matrix, "ship now" vs roadmap, per-section data limitations: **satisfied**.
6. Every required decision made with file paths (C1–C13); JSON-LD choice (`TechArticle` + nested `Product` without offers, `BreadcrumbList`, `WebSite`+`Dataset`, no retired `SearchAction`) is justified; hubs via existing SoC page + new core/API `brand` filter; `lastModified` from `sources[].verified`; `/llms.txt` served; compare policy; "top parts" evaluated and deferred for lack of a signal: **satisfied**.
7. Key events, GSC↔GA4 link (UI-only, correct), UTM convention, Vercel Analytics no / Speed Insights conditional yes, dims-vs-code diff with a concrete register list: **satisfied**.
8. Order PR-A → PR-0 → PR-B → PR-F1…F7, one concern per PR, green CI, merge only on Felipe's go: **satisfied** (see sequencing note in answer 4).
9. `## Concerns` with severities and `## Questions for the author`, open questions 1–3 answered: **satisfied**.

## Answers to the builder's questions

1. **Fonts** — yes, ship on that basis. Measure CLS with PSI after merge; if part-page CLS > 0.1, follow up with `display: "optional"` or an explicit `adjustFontFallback` in its own PR.
2. **Compare** — agreed: `robots: { index: false, follow: true }` + canonical `/compare` for every `?ids=` variant now; curated "X vs Y" SSR landing pages are roadmap, and which comparisons exist IS FELIPE'S CALL.
3. **Hubs** — agreed on both. The core/API `brand` filter (C5: `search.py` `_EXACT_FILTERS`, `/search?brand=`, CLI `--brand`, tests in all three suites) IS in scope for the 0–30-day PRs; it is the constraint-3-compliant way to build `/brands/*`.
4. **PR-0** — yes, open it: remove the `paths:` block from `pull_request` in `.github/workflows/validate.yml`; leave `push: branches: [main]` untouched; nothing else in that file changes. Sequencing: PR-A (restyle) does not need PR-0 — open it immediately. Base PR-B on the existing `handover/seo-audit-and-restyle` branch (rebased onto `main` after PR-0 and PR-A merge) so one PR carries `docs/handovers/**` (handover, plan, this review) together with `docs/seo-audit/**`.
5. **Breadcrumb** — default: 2-level `BreadcrumbList` (Home › part), no visual change. The 3-level variant with the middle crumb linking to the SoC page is a visible change beyond the zip → list it in the audit as a High/low-effort recommendation; shipping it IS FELIPE'S CALL.
6. **Screenshots** — commit at most 6 PNGs, each ≤ 200 KB, under `docs/seo-audit/assets/2026-08-22/`; everything else stays in the scratchpad and is referenced by path in chat.
7. **Header icon** — keep the repo's `mounted` gate and use the zip's SVG sun/moon. The flicker is an inconsistency the zip introduced, so this is exactly the "finish where needed" the mission allows; it is a 3-line edit inside `components/HeaderControls.tsx`, still one of the six files.
8. **GCP writes (B0)** — the builder runs them itself with the logged-in `gcloud` account after Felipe's one-line go in the builder's session: enable `analyticsdata`, `searchconsole`, `pagespeedonline` on `esp-atlas-ga4` and create the PSI API key restricted to `pagespeedonline.googleapis.com` (scratchpad only, delete after). The SA key stays as written in the handover: Felipe mints it on request; builder revokes it (`gcloud iam service-accounts keys delete`) and deletes the file when done. Adding the SA to the GSC property is Felipe's, in the GSC UI.
9. **`SITE_EMOJI`** — leave it (zip keeps `lib/site.ts` identical; an unused export is not worth widening the diff).
10. **Footer `<h2>` → `<p className="footer-title">`** — yes, include in PR-F1. No pixel changes (the class carries the styling), and the heading outline is an SEO concern inside this mission.
11. **`/` rendering** — do not make `/` `force-dynamic`. Use ISR instead: `export const revalidate = 300` on `app/page.tsx` with the same never-throwing `fetchFacets()` (3 s timeout). At build time the fetch fails and the browse section is omitted from the first static render; within five minutes of the first request Next regenerates it with the links; the HTML stays CDN-cached. Keep `sitemap.ts` as it is (`force-dynamic`). If `revalidate` on `/` proves incompatible with anything in Next 16.3.2 during implementation, fall back to the builder's `force-dynamic` variant and say so in the PR body.

Two further notes, binding:

- **Constraint 6 when registering the missing params** (§7): register `brand, soc_ref, from_id, to_id, endpoint, status, path, panel, open, direction, ieee802154, usb_native, has_query` as event-scoped dimensions and `count` as a metric through the Admin API with the SA; leave `url` unregistered. Display names must avoid `-` and `.` (Google rejects them — "WiFi standard" precedent).
- **Scope of PR-F4** after answer 11: "Browse by chip" links + SoC-page `<h2>` hub section + `ItemList` JSON-LD; "Browse by brand" enters only once PR-F5 has merged.

## Closing

Builder is now the primary session. First move (the handover's `next_action`): `git fetch origin && git checkout -b restyle/editorial-newsreader origin/main`, unzip `/Users/fcavalcanti/Downloads/esp-atlas.zip` into a scratchpad dir, copy the six files from checklist item 2 into `apps/web/` (applying answer 7 inside `HeaderControls.tsx`), run `npx next typegen && npx tsc --noEmit && npm run lint && npm run build`, take the 12 screenshots, commit, push, `gh auth switch --user fcavalcantirj && gh pr create …`, switch `gh` back. Then PR-0, then B0 → audit → PR-B, then the fix PRs in the plan's order. Merge each only on Felipe's go.
