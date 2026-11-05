import { mkdtempSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const { chromium } = await import(process.env.ATLAS_PLAYWRIGHT_MODULE || 'playwright');
const base = (process.env.ATLAS_BASE_URL || 'http://127.0.0.1:4175').replace(/\/$/, '');
const apiBase = (process.env.ATLAS_API_BASE_URL || 'http://127.0.0.1:4180').replace(/\/$/, '');
const outputDir = process.env.ATLAS_OUTPUT_DIR || mkdtempSync(join(tmpdir(), 'esp-atlas-browser-'));
mkdirSync(outputDir, { recursive: true });
const browserOptions = { headless: true, ...(process.env.ATLAS_BROWSER_EXECUTABLE ? { executablePath: process.env.ATLAS_BROWSER_EXECUTABLE } : {}) };

import fs from 'node:fs';
const out=outputDir; const b=await chromium.launch(browserOptions);
const results=[],errors=[],consoleErrors=[],requests=[]; const routeList=['/','/boards','/modules','/socs','/brands','/brands/lcdwiki','/parts/lcdwiki-es3c28p','/firmware','/firmware/circuitpython','/wizard','/compare?ids=m5cardputer,esp32-s3','/debug','/status','/submit','/how-we-work'];
const p=await b.newPage({viewport:{width:1440,height:1000},colorScheme:'dark',reducedMotion:'reduce'});p.on('pageerror',e=>errors.push({url:p.url(),message:e.message}));p.on('console',m=>{if(m.type()==='error')consoleErrors.push({url:p.url(),message:m.text()})});p.on('request',r=>{if(!r.url().startsWith(base)&&!r.url().startsWith(apiBase))requests.push(r.url())});
await p.route(/https?:\/\/([^/]*\.)?(google-analytics\.com|googletagmanager\.com)\//,r=>r.fulfill({status:200,contentType:'application/javascript',body:'/* Local QA: analytics suppressed. */'}));
async function inspect(key,capture=true){
 const metrics=await p.evaluate(()=>{const main=document.querySelector('main');return{width:innerWidth,doc:document.documentElement.scrollWidth,h1:main?.querySelector('h1')?.textContent,main:!!main,header:document.querySelector('header')?.getBoundingClientRect().width,footer:document.querySelector('footer')?.getBoundingClientRect().width,clippedHeadings:[...document.querySelectorAll('h1,h2,h3')].filter(el=>el.getClientRects().length&&el.scrollWidth>el.clientWidth+2).map(el=>({text:el.textContent,width:el.clientWidth,scroll:el.scrollWidth}))}});
 results.push({key,...metrics});if(capture)await p.screenshot({path:out+'/'+key+'.png'});
}
try{
 for(const width of [390,1440]){
  await p.setViewportSize({width,height:1000});
  for(const route of routeList){await p.goto(base+route,{waitUntil:'domcontentloaded'});await p.locator('main h1').first().waitFor({timeout:30000});await p.waitForTimeout(250);await inspect('route-'+route.replace(/[^a-z0-9]/gi,'_')+'-'+width);}
 }
 for(const width of [390,1440])for(const theme of ['dark','light'])for(const scale of [1,2])for(const lens of ['map','silicon','hardware','firmware','projects','evidence']){
  await p.setViewportSize({width,height:1000});await p.goto(base+'/atlas?part=m5cardputer&firmware=ruview&recipe=m5cardputer__ruview&focus=firmware&lens='+lens,{waitUntil:'domcontentloaded'});await p.locator('#atlas-record').waitFor();await p.evaluate(t=>document.documentElement.dataset.theme=t,theme);await p.waitForTimeout(150);
  if(scale===2)await p.evaluate(()=>{const els=[...document.querySelectorAll('body,body *')].filter(el=>el instanceof HTMLElement).map(el=>[el,parseFloat(getComputedStyle(el).fontSize)]);for(const[el,size]of els)el.style.fontSize=size*2+'px'});
  await inspect(`atlas-${lens}-${width}-${theme}-${scale}x`,scale===2||theme==='dark');
 }
 fs.writeFileSync(out+'/browser-matrix.json',JSON.stringify({results,errors,consoleErrors,requests:[...new Set(requests)]},null,2));if(results.some(r=>r.doc>r.width+1||r.clippedHeadings.length)||errors.length||consoleErrors.length) throw new Error('Layout or browser error; inspect browser-matrix.json');console.log(JSON.stringify({outputDir,cases:results.length,overflow:results.filter(r=>r.doc>r.width+1||r.clippedHeadings.length),errors,consoleErrors:consoleErrors.slice(0,12),external:[...new Set(requests)].slice(0,12)}));
}finally{await b.close();console.log('Browser evidence:',outputDir)}
