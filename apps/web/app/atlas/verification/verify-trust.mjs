#!/usr/bin/env node
// Read-only production-preview trust checks. Requires a built/running web app,
// its live API, and Playwright supplied by the caller; no hardware is accessed.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const repository = resolve(root, '../..');
const out = resolve(process.env.ATLAS_OUTPUT_DIR || await fs.mkdtemp(join(tmpdir(), 'atlas-trust-')));
const base = (process.env.ATLAS_BASE_URL || 'http://localhost:4175').replace(/\/+$/, '');
const apiBase = (process.env.ATLAS_API_BASE_URL || 'http://localhost:4180').replace(/\/+$/, '');
const { chromium } = await import(process.env.ATLAS_PLAYWRIGHT_MODULE || 'playwright');
const files = ['components/atlas/AtlasExplorer.tsx', 'components/atlas/AtlasInspector.tsx', 'components/atlas/AtlasUnavailable.tsx',
  'components/atlas/AtlasGraph.tsx', 'components/atlas/AtlasExplorer.module.css', 'components/atlas/AtlasGraph.module.css',
  'lib/atlas-route.ts', 'lib/atlas-detail.ts', 'lib/atlas-model.ts', 'lib/atlas-load.ts', 'lib/atlas-server.ts',
  'lib/atlas-graph.ts', 'app/atlas/page.tsx', 'app/atlas/error.tsx', 'app/atlas/loading.tsx'];
const hash = text => createHash('sha256').update(text).digest('hex');
async function hashes() { return Object.fromEntries(await Promise.all(files.map(async path => [path, hash(await fs.readFile(`${root}/${path}`))]))); }
await fs.mkdir(out, { recursive: true });
const before = await hashes();
const manifestPath = process.env.ATLAS_SOURCE_MANIFEST || null;
const manifestBytes = manifestPath ? await fs.readFile(manifestPath) : null;
const manifest = manifestBytes ? JSON.parse(manifestBytes) : {};
async function manifestMismatches() {
  const checked = await Promise.all(Object.entries(manifest).map(async ([path, expected]) => ({ path,
    actual: hash(await fs.readFile(resolve(repository, path))), expected })));
  return checked.filter(entry => entry.actual !== entry.expected);
}
const report = { started: new Date().toISOString(), buildId: (await fs.readFile(`${root}/.next/BUILD_ID`, 'utf8')).trim(),
  sourceHashes: before, scopeHash: hash(JSON.stringify(before)), tests: [], browser: [], screenshots: [],
  manifestPath, manifestHash: manifestBytes ? hash(manifestBytes) : null, manifestFileCount: Object.keys(manifest).length,
  manifestMismatchesBefore: await manifestMismatches(),
  scope: 'Frozen production preview; isolated headless Chromium; no hardware actions; Google analytics blocked before navigation.' };
const recipeResponse = await fetch(`${apiBase}/recipes?board=m5cardputer`, { signal: AbortSignal.timeout(15000) });
assert.equal(recipeResponse.ok, true, 'The live recipe oracle must answer successfully.');
const ruview = (await recipeResponse.json()).results.find(recipe => recipe.id === 'm5cardputer__ruview');
assert.ok(ruview?.notes, 'The live catalog must include the Cardputer/RuView caveat.');
const browser = await chromium.launch({ headless: true, ...(process.env.ATLAS_BROWSER_EXECUTABLE
  ? { executablePath: process.env.ATLAS_BROWSER_EXECUTABLE } : {}) });
const goal = 'solar pump & café / literal?';
const query = new URLSearchParams({ lens: 'evidence', part: 'm5cardputer', firmware: 'ruview', recipe: ruview.id, goal, focus: 'firmware' });

async function pageFor(name, width = 1440) {
  const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 1000 }, reducedMotion: 'reduce' });
  const log = { name, pageErrors: [], console: [], blockedAnalytics: [], failedRequests: [], navigationRequests: [] };
  report.browser.push(log);
  await context.route('**/*', async route => {
    const host = new URL(route.request().url()).hostname;
    if (['googletagmanager.com', 'google-analytics.com'].some(domain => host === domain || host.endsWith(`.${domain}`))) {
      log.blockedAnalytics.push(route.request().url());
      return route.fulfill({ status: 200, contentType: 'application/javascript', body: '' });
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', error => log.pageErrors.push(error.message));
  page.on('console', message => {
    if (['error', 'warning'].includes(message.type())) log.console.push({ type: message.type(), text: message.text(), location: message.location() });
  });
  page.on('requestfailed', request => log.failedRequests.push({ url: request.url(), failure: request.failure() }));
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.origin === base && (request.isNavigationRequest() || url.searchParams.has('_rsc'))) log.navigationRequests.push(request.url());
  });
  return { page, context, log };
}
async function go(page, path) {
  const response = await page.goto(`${base}${path}`, { waitUntil: 'domcontentloaded' });
  assert.equal(response.status(), 200);
  await page.locator('main h1').waitFor();
}
function assertQuiet(log) {
  assert.deepEqual(log.pageErrors, []);
  assert.deepEqual(log.console.filter(entry => /hydration|hydrated|did not match|server rendered|react error/i.test(entry.text)), []);
}
async function screenshot(page, name) {
  const path = `${out}/${name}.png`;
  await page.screenshot({ path }); report.screenshots.push(path);
}
async function check(name, run) {
  try { const evidence = await run(); report.tests.push({ name, pass: true, ...evidence }); console.log(`PASS ${name}`); }
  catch (error) { report.tests.push({ name, pass: false, error: error.stack }); console.log(`FAIL ${name}: ${error.message}`); }
  await fs.writeFile(`${out}/report.json`, JSON.stringify(report, null, 2));
}
function detail(id, body = `Cited notes for ${id}.`) {
  return { id, body, chain: { soc: null, module: null }, sources: [{ field: '*', url: 'https://vendor.example.test/source', verified: '2026-11-05' }] };
}

try {
  await check('RuView exact pair preserves full caveat, citations and absent artifact on phone', async () => {
    const { page, context, log } = await pageFor('ruview-phone', 390);
    try {
      await go(page, `/atlas?${query}`);
      const evidence = page.locator(`[data-atlas-recipe="${ruview.id}"]`); await evidence.waitFor();
      const caveat = evidence.locator('p').filter({ hasText: ruview.notes });
      assert.equal(await caveat.textContent(), ruview.notes.trim());
      assert.match(await evidence.innerText(), /No installation artifact is recorded for this pairing/);
      for (const source of ruview.sources) assert.equal(await evidence.locator(`a[href="${source.url}"]`).count(), 1);
      const geometry = await caveat.evaluate(element => ({ paragraphHeight: element.clientHeight, paragraphScrollHeight: element.scrollHeight,
        viewport: document.documentElement.clientWidth, document: document.documentElement.scrollWidth }));
      assert.equal(geometry.viewport, geometry.document); assert.equal(geometry.paragraphHeight, geometry.paragraphScrollHeight);
      await evidence.scrollIntoViewIfNeeded(); await screenshot(page, 'ruview-phone-evidence');
      await evidence.getByText('No installation artifact is recorded for this pairing.', { exact: true }).scrollIntoViewIfNeeded();
      await evidence.locator('ul').evaluate(element => element.scrollIntoView({ behavior: 'instant', block: 'start' }));
      await screenshot(page, 'ruview-phone-sources'); assertQuiet(log);
      return { geometry, caveatLength: ruview.notes.length, sources: ruview.sources.length, recipe: ruview.id };
    } finally { await context.close(); }
  });

  await check('Native history preserves exact pair and goal through lenses, selection, Back, Forward and reload', async () => {
    const { page, context, log } = await pageFor('native-history');
    try {
      await go(page, `/atlas?${query}`); await page.locator(`[data-atlas-recipe="${ruview.id}"]`).waitFor();
      const selectedNavigation = () => log.navigationRequests.filter(value => {
        const url = new URL(value); return url.pathname === '/atlas' && url.searchParams.has('lens');
      });
      const startRequests = selectedNavigation().length;
      const assertContext = (lens, part = 'm5cardputer', recipe = ruview.id) => {
        const params = new URL(page.url()).searchParams;
        assert.equal(params.get('lens'), lens); assert.equal(params.get('part'), part);
        assert.equal(params.get('firmware'), 'ruview'); assert.equal(params.get('goal'), goal); assert.equal(params.get('recipe'), recipe);
      };
      for (const lens of ['map', 'silicon', 'hardware', 'firmware', 'projects', 'evidence']) {
        await page.locator('nav[aria-label="Atlas lenses"] a').filter({ hasText: new RegExp(lens, 'i') }).click();
        await page.waitForURL(url => url.searchParams.get('lens') === lens);
          assertContext(lens);
      }
      assert.equal(selectedNavigation().length, startRequests, 'Lens changes must remain local history changes');
      await page.goBack(); await page.waitForURL(url => url.searchParams.get('lens') === 'projects'); assertContext('projects');
      await page.goForward(); await page.waitForURL(url => url.searchParams.get('lens') === 'evidence'); assertContext('evidence');
      await page.locator('#atlas-record').selectOption('part:esp32-s3');
      await page.waitForURL(url => url.searchParams.get('part') === 'esp32-s3'); assertContext('evidence', 'esp32-s3', null);
      await page.goBack(); await page.locator(`[data-atlas-recipe="${ruview.id}"]`).waitFor(); assertContext('evidence');
      await page.goForward(); await page.waitForURL(url => url.searchParams.get('part') === 'esp32-s3'); assertContext('evidence', 'esp32-s3', null);
      await page.reload({ waitUntil: 'domcontentloaded' }); await page.locator('#atlas-record').waitFor();
      assertContext('evidence', 'esp32-s3', null); assert.equal(await page.locator('#atlas-record').inputValue(), 'part:esp32-s3');
      await go(page, `/atlas?${query}`); await page.locator(`[data-atlas-recipe="${ruview.id}"]`).waitFor();
      await page.reload({ waitUntil: 'domcontentloaded' }); await page.locator(`[data-atlas-recipe="${ruview.id}"]`).waitFor(); assertContext('evidence');
      await screenshot(page, 'exact-pair-desktop-reloaded'); assertQuiet(log);
      return { allSixLenses: true, back: true, forward: true, reload: true, sourceRecipe: ruview.id, goal,
        selectedQueryFetchesDuringLensChanges: selectedNavigation().slice(0, startRequests) };
    } finally { await context.close(); }
  });

  await check('Mismatched URL cannot display another exact recipe', async () => {
    const { page, context, log } = await pageFor('mismatched-recipe');
    try {
      await go(page, '/atlas?lens=evidence&part=esp32-s3&firmware=ruview&recipe=m5cardputer__ruview');
      await page.getByText('This URL does not resolve to a matching record or exact recipe.', { exact: false }).waitFor();
      assert.equal(await page.locator('[data-atlas-recipe]').count(), 0);
      assert.equal(new URL(page.url()).searchParams.get('recipe'), ruview.id); assertQuiet(log);
      return { requestedIdRetained: true, substitutedRecipe: false };
    } finally { await context.close(); }
  });

  for (const mode of ['404', '503', 'malformed-source', 'malformed-body', 'malformed-chain', 'wrong-id']) {
    await check(`Detail ${mode} remains recoverable with selection intact`, async () => {
      const { page, context, log } = await pageFor(`detail-${mode}`); let interceptions = 0;
      try {
        await page.route('**/parts/esp32-s3', route => {
          interceptions++;
          if (mode === '404' || mode === '503') return route.fulfill({ status: Number(mode), contentType: 'application/json', body: '{}' });
          const value = detail('esp32-s3');
          if (mode === 'malformed-source') value.sources = [null];
          if (mode === 'malformed-body') value.body = { invalid: true };
          if (mode === 'malformed-chain') value.chain = true;
          if (mode === 'wrong-id') value.id = 'another-chip';
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(value) });
        });
        await go(page, '/atlas?lens=silicon&part=esp32-s3&focus=part&goal=keep-me');
        await page.getByRole('button', { name: 'Retry details', exact: true }).waitFor();
        const expected = mode === '404' ? 'This record is no longer available at the API.' : 'The detail request failed. The catalog selection is still here.';
        assert.equal(await page.getByText(expected, { exact: true }).isVisible(), true);
        assert.equal(new URL(page.url()).searchParams.get('part'), 'esp32-s3');
        assert.equal(new URL(page.url()).searchParams.get('goal'), 'keep-me');
        assert.ok(interceptions > 0); assertQuiet(log);
        if (mode === 'malformed-source') { await page.getByRole('button', { name: 'Retry details' }).scrollIntoViewIfNeeded(); await screenshot(page, 'malformed-source-recoverable'); }
        return { interceptions, retainedPart: 'esp32-s3', retainedGoal: 'keep-me' };
      } finally { await context.close(); }
    });
  }

  await check('Retry details recovers a failed request without clearing selected context', async () => {
    const { page, context, log } = await pageFor('retry-recovery'); let calls = 0;
    try {
      await page.route('**/parts/esp32-s3', route => ++calls === 1
        ? route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
        : route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(detail('esp32-s3', 'Recovered source record.')) }));
      await go(page, '/atlas?lens=silicon&part=esp32-s3&focus=part&goal=keep-me');
      await page.getByRole('button', { name: 'Retry details', exact: true }).click();
      await page.getByText('Notes from the part record', { exact: true }).click();
      assert.equal(await page.getByText('Recovered source record.', { exact: true }).isVisible(), true);
      assert.equal(new URL(page.url()).searchParams.get('part'), 'esp32-s3'); assert.equal(new URL(page.url()).searchParams.get('goal'), 'keep-me');
      assert.equal(calls, 2); assertQuiet(log); return { calls, selectedContextRetained: true };
    } finally { await context.close(); }
  });

  await check('Changing selection aborts stale detail and never replaces the current record', async () => {
    const { page, context, log } = await pageFor('stale-request');
    let release, arrived, finished;
    const ready = new Promise(resolve => { arrived = resolve; });
    const held = new Promise(resolve => { release = resolve; });
    const done = new Promise(resolve => { finished = resolve; });
    let lateFulfillment;
    try {
      await page.addInitScript(() => {
        const original = window.fetch;
        window.__atlasDetailRequests = [];
        window.fetch = function(input, init) {
          if (String(input).includes('/parts/')) {
            const observed = { url: String(input), aborted: init?.signal?.aborted ?? false };
            window.__atlasDetailRequests.push(observed);
            init?.signal?.addEventListener('abort', () => { observed.aborted = true; });
          }
          return original.call(this, input, init);
        };
      });
      await page.route('**/parts/esp32-s3', async route => {
        arrived(); await held;
        try { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(detail('esp32-s3', 'STALE S3 RESPONSE MUST NEVER REPLACE C6.')) }); lateFulfillment = 'completed'; }
        catch (error) { lateFulfillment = error.message; }
        finally { finished(); }
      });
      await page.route('**/parts/esp32-c6', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(detail('esp32-c6', 'Current C6 source record.')) }));
      await go(page, '/atlas?lens=silicon&part=esp32-s3&focus=part&goal=keep-me'); await ready;
      await page.locator('#atlas-record').selectOption('part:esp32-c6');
      await page.waitForURL(url => url.searchParams.get('part') === 'esp32-c6');
      await page.getByText('Notes from the part record', { exact: true }).click();
      assert.equal(await page.getByText('Current C6 source record.', { exact: true }).isVisible(), true);
      await page.waitForFunction(() => window.__atlasDetailRequests.some(request => request.url.endsWith('/parts/esp32-s3') && request.aborted));
      const abortedRequest = await page.evaluate(() => window.__atlasDetailRequests.find(request => request.url.endsWith('/parts/esp32-s3')));
      release(); await done;
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.equal(await page.getByText('STALE S3 RESPONSE MUST NEVER REPLACE C6.', { exact: true }).count(), 0);
      assert.equal(await page.getByText('Current C6 source record.', { exact: true }).isVisible(), true);
      assert.equal(await page.locator('#atlas-record').inputValue(), 'part:esp32-c6');
      assert.equal(new URL(page.url()).searchParams.get('goal'), 'keep-me'); assertQuiet(log);
      await screenshot(page, 'stale-request-current-selection');
      return { abortedRequest, lateFulfillment, currentPart: 'esp32-c6', staleContentVisible: false };
    } finally { release?.(); await context.close(); }
  });

  await check('Unsafe detail source schemes remain text, without a navigable unsafe link', async () => {
    const { page, context, log } = await pageFor('unsafe-source');
    try {
      const value = detail('esp32-s3'); value.sources = [{ field: '*', url: 'javascript:alert(1)', verified: '2026-11-05' }];
      await page.route('**/parts/esp32-s3', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(value) }));
      await go(page, '/atlas?lens=silicon&part=esp32-s3&focus=part');
      await page.getByText('Source link unavailable', { exact: true }).waitFor();
      assert.equal(await page.locator('a[href^="javascript:"]').count(), 0); assertQuiet(log);
      return { unsafeLinkCount: 0 };
    } finally { await context.close(); }
  });
} finally {
  await browser.close();
  const after = await hashes();
  report.sourceStable = JSON.stringify(before) === JSON.stringify(after);
  report.manifestMismatchesAfter = await manifestMismatches();
  report.finished = new Date().toISOString();
  report.pass = report.tests.every(test => test.pass) && report.sourceStable
    && report.manifestMismatchesBefore.length === 0 && report.manifestMismatchesAfter.length === 0;
  report.analyticsBlocked = report.browser.reduce((sum, item) => sum + item.blockedAnalytics.length, 0);
  report.pageErrors = report.browser.flatMap(item => item.pageErrors);
  report.hydrationConsole = report.browser.flatMap(item => item.console.filter(entry => /hydration|hydrated|did not match|server rendered|react error/i.test(entry.text)));
  await fs.writeFile(`${out}/report.json`, JSON.stringify(report, null, 2));
  await fs.writeFile(`${out}/source-sha256.txt`, files.map(file => `${before[file]}  ${file}`).join('\n') + '\n');
  console.log(JSON.stringify({ pass: report.pass, tests: report.tests.length, failed: report.tests.filter(test => !test.pass).map(test => test.name),
    buildId: report.buildId, scopeHash: report.scopeHash, sourceStable: report.sourceStable, analyticsBlocked: report.analyticsBlocked,
    manifestHash: report.manifestHash, manifestFileCount: report.manifestFileCount,
    manifestMismatchesBefore: report.manifestMismatchesBefore, manifestMismatchesAfter: report.manifestMismatchesAfter,
    pageErrors: report.pageErrors, hydrationConsole: report.hydrationConsole, evidence: `${out}/report.json` }, null, 2));
  if (!report.pass) process.exitCode = 1;
}
