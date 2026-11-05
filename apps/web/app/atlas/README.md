# Atlas workspace

This first production slice adds `/atlas` and carries the approved bone, black and orange visual language into the shared shell. Existing search, wizard, record, comparison, installation, verification, submission and status routes keep their implementations and canonical URLs.

## Data and trust contract

- Load the complete `/parts`, `/firmware` and `/recipes` collections concurrently. Preserve the existing `catalog` cache tag, one-hour fetch revalidation and bounded transport retry. A missing, malformed, inconsistent or truncated collection is an error, never a successful empty atlas.
- Draw only recorded hardware lineage and exact recipe edges. A board's module reference takes precedence over its inherited silicon reference. Shared silicon does not establish compatibility; unresolved references are disclosed rather than fabricated.
- Preserve every recipe ID, endpoint, status, note and source. Resolve an explicit recipe only when its ID, board and firmware all match. The API's combined board/firmware filters are not assumed to intersect.
- Keep all five evidence tiers and unknown future statuses visible. RuView discovery caveats and absent artifacts remain intact. Broken pairings have documentation and cited history, with no installation action in this workspace.
- Load and validate part detail on selection; abort abandoned requests and preserve a recoverable error state. Inherited specifications remain on their originating records. Repository popularity is shown only with its recorded observation date and source.

## Interaction contract

Selection and lens changes use real, shareable URL parameters and native history integrated with Next's router. They preserve the other endpoint, exact recipe and goal where applicable without refetching the full catalog. Changing an endpoint clears the former exact recipe. Browser Back, Forward and reload restore the URL state.

The graph offers pan, rotation, zoom, Fit and full screen. A single keyboard graph stop and the complete record selector avoid hundreds of Tab stops. Hover previews have a real inspect action and pointer/focus grace. Labels stay upright and sparse. SVG coordinates are rounded consistently across server and browser rendering.

The collection name filter is explicitly a lookup within the loaded view. Alias search, ranking, capability filters and project recommendations remain in the existing server-backed search and finder workflows; the Projects lens links to those workspaces. This slice does not replace them with a local substring ranking or prototype simulation.

## Boundaries

No prototype catalog, simulated installer, new backend endpoint, generated source record or fabricated activity metric is imported. Shared providers, system/light/dark themes, saved text sizes, prepaint behavior, metadata, analytics and prior navigation destinations are retained. The interactive workspace is noindex with `/atlas` as its canonical; existing indexable record pages are unchanged.

Validation covers the pure model, collection loading, exact selection, malformed details, geometry and URL state, plus isolated browser checks against a production build and the real API. Physical hardware and native screen-reader acceptance are separate from these browser checks. Full repository lint has a pre-existing reserved-file `react-hooks/set-state-in-effect` error in `components/verify/ConnectTroubleshooter.tsx`; changed files are checked separately and the existing failure is reported rather than suppressed.

## Repeat the checks

From `apps/web`, run `npm test`, `npx tsc --noEmit` and `npm run build`. The browser checks under `app/atlas/verification/` use a running production build and the actual catalog API. They suppress Google Analytics traffic and never request a serial device, download firmware or flash hardware.

```sh
node app/atlas/verification/verify-layout.mjs
node app/atlas/verification/verify-workflows.mjs
node app/atlas/verification/verify-shell.mjs
node app/atlas/verification/verify-trust.mjs
node app/atlas/verification/verify-graph.mjs
```

Playwright must be available to the runner. Set `ATLAS_PLAYWRIGHT_MODULE` to its importable module or module path when it is installed outside this project; `ATLAS_BROWSER_EXECUTABLE` optionally selects an installed Chromium browser. `ATLAS_BASE_URL` defaults to the local preview on port 4175, and `ATLAS_API_BASE_URL` to the local API on port 4180. The graph verifier uses `ATLAS_API_ORIGIN` for its API request allowlist, with the same port default. `ATLAS_OUTPUT_DIR` optionally chooses where evidence is written; otherwise each run creates and prints a temporary directory. No developer-specific path is stored in the scripts.

The layout check covers all 15 existing page routes at phone/desktop widths and all six atlas views across themes and actual doubled text. The workflow check exercises the merged LCDWIKI record, server alias search, a nearby unmatched SKU, saved display preferences, the broken-recipe presentation and six-part mixed comparison. The trust check injects explicit failed/malformed detail responses and verifies recovery, cancellation and URL history. The graph check covers pointer, keyboard and emulated touch interactions, camera controls, fullscreen, target sizes and reflow. Their observed results are review evidence for the tested source and catalog, not guarantees about every browser or physical device.
