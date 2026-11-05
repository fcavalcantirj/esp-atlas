import { mkdtempSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const { chromium } = await import(process.env.ATLAS_PLAYWRIGHT_MODULE || 'playwright');
const base = (process.env.ATLAS_BASE_URL || 'http://127.0.0.1:4175').replace(/\/$/, '');
const outputDir = process.env.ATLAS_OUTPUT_DIR || mkdtempSync(join(tmpdir(), 'esp-atlas-browser-'));
mkdirSync(outputDir, { recursive: true });
const browserOptions = { headless: true, ...(process.env.ATLAS_BROWSER_EXECUTABLE ? { executablePath: process.env.ATLAS_BROWSER_EXECUTABLE } : {}) };

import assert from 'node:assert/strict';import fs from 'node:fs';
const b=await chromium.launch(browserOptions);const p=await b.newPage({viewport:{width:1440,height:1000},colorScheme:'dark'});const errors=[],cases=[];p.on('pageerror',e=>errors.push(e.message));await p.route(/https?:\/\/([^/]*\.)?(google-analytics\.com|googletagmanager\.com)\//,r=>r.fulfill({status:200,contentType:'application/javascript',body:'/* QA: analytics disabled */'}));
try {
await p.goto(base+'/atlas?lens=projects');await p.locator('#atlas-keyword').fill('ES3C28P');await p.locator('form[action="/wizard"] button').click();await p.waitForURL('**/wizard?q=ES3C28P');await p.locator('main a[href="/parts/lcdwiki-es3c28p"]').first().waitFor();cases.push('Projects keyword handoff returns exact new LCDWIKI part through real server search');
await p.goto(base+'/atlas?lens=hardware');await p.locator('#atlas-name-filter').fill('es3c28p');await p.locator('section[aria-label="Hardware"] button').first().waitFor();assert.equal(await p.locator('section[aria-label="Hardware"] button').count(),1);await p.locator('section[aria-label="Hardware"] button').click();await p.waitForURL('**part=lcdwiki-es3c28p**');await p.locator('aside a[href="/parts/lcdwiki-es3c28p"]').waitFor();await p.locator('aside').getByText('lcdwiki.com',{exact:false}).first().waitFor();cases.push('New merged LCDWIKI part selectable with real vendor sources');
await p.getByRole('button',{name:'Larger text',exact:true}).click();const scale=await p.evaluate(()=>localStorage.getItem('esp-atlas:font-scale'));assert.ok(Number(scale)>1);await p.reload();assert.equal(await p.evaluate(()=>document.documentElement.style.getPropertyValue('--font-scale')),scale);await p.getByRole('button',{name:'Switch to light theme',exact:true}).click();await p.reload();assert.equal(await p.evaluate(()=>document.documentElement.dataset.theme),'light');cases.push('Saved theme and enlarged text persist through reload');
const apiBase = (process.env.ATLAS_API_BASE_URL || 'http://127.0.0.1:4180').replace(/\/$/, '');
const c5Response = await fetch(apiBase + '/recipes?board=esp32-c5-devkitc-1');
assert.equal(c5Response.status, 200);
const c5Recipes = (await c5Response.json()).results;
const brokenRecipe = c5Recipes.find(recipe => recipe.id === 'esp32-c5-devkitc-1__esp32marauder');
assert.equal(brokenRecipe.status, 'broken');
await p.goto(base+'/atlas?part=esp32-c5-devkitc-1&firmware=esp32marauder&recipe=esp32-c5-devkitc-1__esp32marauder&lens=evidence');
const brokenEvidence = p.locator('[data-atlas-recipe]');
await brokenEvidence.waitFor();
const brokenText = await brokenEvidence.innerText();
assert.match(brokenText, /Installation is unavailable for this broken pairing/);
assert.match(brokenText, /Artifact citation retained/);
assert.ok(brokenText.includes(brokenRecipe.notes));
assert.equal(await brokenEvidence.locator('button').count(), 0);
const brokenLinks = await brokenEvidence.locator('a').evaluateAll(links => links.map(link => link.href));
const recordedArtifacts = [brokenRecipe.flash?.bin_url, brokenRecipe.flash?.manifest_url].filter(Boolean);
for (const artifact of recordedArtifacts) {
  assert.ok(brokenText.includes(artifact), 'Recorded artifact URL remains readable');
  assert.ok(!brokenLinks.includes(artifact), 'Recorded artifact URL must not be an anchor');
}
for (const href of brokenLinks) {
  const url = new URL(href);
  assert.doesNotMatch(url.pathname, /\/(?:manifest\/|flash-bin(?:\/|$))|\.(?:bin|uf2|hex|elf|zip)$/i);
}
for (const source of brokenRecipe.sources) assert.ok(brokenText.includes(source.verified), 'Source date remains readable');
await brokenEvidence.locator('a[href*="/wiki/"]').waitFor();
cases.push('Broken exact recipe keeps full notes, artifact URL/date and documentation while denying direct artifact and manifest/proxy handoffs');
const positive = c5Recipes.find(recipe => recipe.id === 'esp32-c5-devkitc-1__bruce');
assert.equal(positive.status, 'known-good');
const positiveArtifact = positive.sources.find(source => source.url === positive.flash?.bin_url || source.url === positive.flash?.manifest_url);
assert.ok(positiveArtifact, 'Positive control has a cited installation artifact');
await p.goto(base + '/atlas?part=' + positive.board + '&firmware=' + positive.firmware + '&recipe=' + positive.id + '&lens=evidence');
const positiveEvidence = p.locator('[data-atlas-recipe]');
await positiveEvidence.waitFor();
assert.ok((await positiveEvidence.locator('a').evaluateAll(links => links.map(link => link.href))).includes(positiveArtifact.url));
cases.push('Known-good exact recipe retains its active artifact citation; no link followed or binary downloaded');
await p.goto(base+'/wizard?q=es3n28p');await p.waitForTimeout(500);assert.equal(await p.locator('main a[href="/parts/lcdwiki-es3c28p"]').count(),0);cases.push('Nearby unrecorded SKU does not become LCDWIKI touch variant');
await p.goto(base+'/compare?ids=m5cardputer,esp32-s3,esp32-c6,esp32-s3-wroom-1,esp32-c6-wroom-1,lcdwiki-es3c28p');await p.waitForTimeout(500);assert.match(await p.locator('main').innerText(),/Cardputer/);assert.match(await p.locator('main').innerText(),/ESP32-S3/);assert.match(await p.locator('main').innerText(),/ESP32-C6-WROOM-1/);assert.match(await p.locator('main').innerText(),/ESP32-S3-WROOM-1/);assert.equal(new URL(p.url()).searchParams.get('ids').split(',').length,6);cases.push('Existing six-part mixed board/module/silicon comparison remains available');
assert.deepEqual(errors,[]);fs.writeFileSync(outputDir+'/workflows.json',JSON.stringify({pass:true,cases,errors},null,2));console.log(JSON.stringify({cases,errors}));
}finally{await b.close();console.log('Browser evidence:',outputDir)}
