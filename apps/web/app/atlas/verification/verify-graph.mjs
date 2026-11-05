import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
// Real-browser checks for the API-backed atlas graph. No fixtures or hardware.
// Run against a built app with its real local API. Analytics scripts are replaced
// with empty JavaScript before navigation so review does not send GA events.
// Optional exact catalog totals: ATLAS_EXPECTED_NODES / ATLAS_EXPECTED_EDGES.
import path from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
const playwrightModule = process.env.ATLAS_PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = await import(path.isAbsolute(playwrightModule) ? pathToFileURL(playwrightModule).href : playwrightModule);
const out = process.env.ATLAS_OUTPUT_DIR || fs.mkdtempSync(path.join(tmpdir(), 'atlas-graph-review-'));
fs.mkdirSync(out, { recursive: true });
const base = new URL('/atlas', process.env.ATLAS_BASE_URL || 'http://127.0.0.1:4175').href;
const apiOrigin = new URL(process.env.ATLAS_API_ORIGIN || 'http://127.0.0.1:4180').origin;
const allowedOrigins = new Set([new URL(base).origin, apiOrigin, apiOrigin.replace('127.0.0.1', 'localhost')]);
const sourceRoot = fileURLToPath(new URL('../../../', import.meta.url));
const sources=['components/atlas/AtlasGraph.tsx','components/atlas/AtlasGraph.module.css','lib/atlas-graph.ts','lib/atlas-graph.test.ts'];
const fingerprint=()=>Object.fromEntries(sources.map(p=>[p,crypto.createHash('sha256').update(fs.readFileSync(sourceRoot+p)).digest('hex')]));
const before=fingerprint();
const browser=await chromium.launch({headless:true,...(process.env.ATLAS_BROWSER_EXECUTABLE ? { executablePath: process.env.ATLAS_BROWSER_EXECUTABLE } : {})});
const buildFile = path.join(sourceRoot, '.next/BUILD_ID');
const result={buildId:fs.existsSync(buildFile)?fs.readFileSync(buildFile,'utf8').trim():null,baseUrl:base,sourceHashes:before,scenarios:[],errors:[],unexpectedRequests:[],blockedAnalytics:[]};
const errors=result.errors;
async function pageFor(options={}) {const context=await browser.newContext({viewport:{width:1440,height:1050},reducedMotion:'reduce',...options});await context.route(/https?:\/\/([^/]+\.)?(googletagmanager\.com|google-analytics\.com)\//,route=>{result.blockedAnalytics.push(route.request().url());return route.fulfill({status:200,contentType:'application/javascript',body:''});});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/net::ERR_FAILED/.test(m.text()))errors.push(m.text());});page.on('request',r=>{if(!allowedOrigins.has(new URL(r.url()).origin)&&!/https?:\/\/([^/]+\.)?(googletagmanager\.com|google-analytics\.com)\//.test(r.url()))result.unexpectedRequests.push(r.url());});return page;}
try{
 const page=await pageFor();await page.goto(base);await page.locator('[data-atlas-node]').first().waitFor();
 await page.waitForFunction(()=>{const s=document.querySelector('[data-atlas-graph] svg[tabindex]'),r=s?.getBoundingClientRect();return r&&Math.abs(s.viewBox.baseVal.width-r.width)<1&&Math.abs(s.viewBox.baseVal.height-r.height)<1;});const graph=page.locator('[data-atlas-graph]'),svg=graph.locator('svg[tabindex="0"]');const focusGraph=async()=>{await page.getByRole('button',{name:'Enter full screen',exact:true}).focus();await page.keyboard.press('Tab');assert.ok(await svg.evaluate(el=>el===document.activeElement));};
 const nodeCount = await page.locator('[data-atlas-node]').count();
 const edgeCount = await graph.locator('path[data-kind]').count();
 assert.ok(nodeCount > 0 && edgeCount > 0, 'This check requires a populated real catalog');
 if (process.env.ATLAS_EXPECTED_NODES) assert.equal(nodeCount, Number(process.env.ATLAS_EXPECTED_NODES));
 if (process.env.ATLAS_EXPECTED_EDGES) assert.equal(edgeCount, Number(process.env.ATLAS_EXPECTED_EDGES));
 assert.equal(await graph.locator('[tabindex="0"]').count(), 1, 'The graph has one keyboard stop');
 assert.equal(await graph.locator('svg[tabindex="0"]').count(),1);
 const readout = await graph.locator('div').filter({hasText: new RegExp(nodeCount + ' records')}).last().textContent();
 assert.ok(readout.includes(nodeCount + ' records') && readout.includes(edgeCount + ' relationships'));
 result.scenarios.push({name: 'real_catalog', nodes: nodeCount, edges: edgeCount, readout});
 await graph.scrollIntoViewIfNeeded();await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));await page.mouse.move(1,1);
 const cardputer=page.locator('[data-atlas-node="part:m5cardputer"]');
 const point=await cardputer.boundingBox();await page.mouse.move(point.x+point.width/2,point.y+point.height/2,{steps:5});await page.getByRole('region',{name:'Cardputer'}).waitFor();await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const button=page.getByRole('button',{name:'Inspect record',exact:false});const box=await button.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:14});await page.waitForTimeout(700);assert.ok(await button.isVisible());await page.screenshot({path:out+'/desktop-hover.png'});await button.click();await page.waitForURL(/part=m5cardputer/);assert.equal(await page.getByRole('region',{name:'Cardputer'}).count(),0);
 result.scenarios.push({name:'pointer_card_travel_and_inspect',url:page.url()});
 const selectedURL=page.url();await page.goBack();await page.waitForURL(url=>!url.searchParams.has('part'));await page.goForward();await page.waitForURL(/part=m5cardputer/);await page.reload();await svg.waitFor();assert.match(await svg.getAttribute('aria-label'),/Cardputer selected/);assert.equal(page.url(),selectedURL);result.scenarios.push({name:'native_history_back_forward_and_reload',url:page.url()});
 for(let i=0;i<12;i++)await page.getByRole('button',{name:'Rotate map clockwise',exact:true}).click();
 assert.equal(await graph.getByLabel('Map rotation',{exact:true}).textContent(),'0°');
 for(let i=0;i<6;i++)await page.getByRole('button',{name:'Zoom map in',exact:true}).click();
 assert.equal(await graph.getByLabel('Map zoom',{exact:true}).textContent(),'250%');assert.equal(page.url(),selectedURL);
 const nodeBefore=await cardputer.boundingBox(),frame=await svg.boundingBox();
 await page.mouse.move(frame.x+frame.width*.52,frame.y+frame.height*.52);await page.mouse.down();await page.mouse.move(frame.x+frame.width*.62,frame.y+frame.height*.58,{steps:10});await page.mouse.up();await page.waitForTimeout(200);assert.equal(page.url(),selectedURL);const nodeAfter=await cardputer.boundingBox();assert.ok(Math.abs(nodeAfter.x-nodeBefore.x)>20);
 await page.getByRole('button',{name:'Fit',exact:true}).click();assert.equal(await graph.getByLabel('Map zoom',{exact:true}).textContent(),'100%');assert.equal(await graph.getByLabel('Map rotation',{exact:true}).textContent(),'0°');assert.equal(page.url(),selectedURL);
 result.scenarios.push({name:'360_zoom_drag_fit',retainedURL:page.url()});
 await page.mouse.move(1,1);await focusGraph();
 for (const key of ['Enter', 'Space']) { await page.keyboard.press(key); assert.equal(page.url(), selectedURL); assert.ok(await svg.evaluate(el => el === document.activeElement)); }
 const beforeKeys = await cardputer.boundingBox();
 await page.keyboard.press('ArrowRight');
 assert.ok((await cardputer.boundingBox()).x > beforeKeys.x + 30);
 await page.keyboard.press('+');assert.equal(await graph.getByLabel('Map zoom',{exact:true}).textContent(),'125%');
 await page.keyboard.press(']');assert.equal(await graph.getByLabel('Map rotation',{exact:true}).textContent(),'30°');
 await page.keyboard.press('Home');assert.equal(await graph.getByLabel('Map zoom',{exact:true}).textContent(),'100%');assert.equal(await graph.getByLabel('Map rotation',{exact:true}).textContent(),'0°');
 await page.keyboard.press('Enter');assert.equal(page.url(),selectedURL);
 result.scenarios.push({name:'keyboard_enter_space_pan_zoom_rotation_home'});
 await page.waitForTimeout(650);assert.equal(await page.getByRole('region',{name:'Cardputer'}).count(),1);
 await page.keyboard.press('Tab');assert.ok(await page.getByRole('button',{name:'Close record preview',exact:true}).evaluate(el=>el===document.activeElement));
 await page.keyboard.press('Tab');assert.ok(await button.evaluate(el=>el===document.activeElement));await page.waitForTimeout(650);assert.ok(await button.isVisible());
 await page.keyboard.press('Shift+Tab');assert.ok(await page.getByRole('button',{name:'Close record preview',exact:true}).evaluate(el=>el===document.activeElement));
 await page.keyboard.press('Shift+Tab');assert.ok(await svg.evaluate(el=>el===document.activeElement));await page.waitForTimeout(650);assert.ok(await button.isVisible());
 await page.keyboard.press('Shift+Tab');await page.waitForTimeout(700);assert.equal(await button.count(),0);
 await focusGraph();await page.keyboard.press('Tab');await page.keyboard.press('Tab');await page.keyboard.press('Tab');await page.waitForTimeout(700);assert.equal(await button.count(),0);assert.ok(!await graph.evaluate(el=>el.contains(document.activeElement)));
 await focusGraph();await page.keyboard.press('Escape');assert.equal(await button.count(),0);assert.equal(page.url(),selectedURL);
 result.scenarios.push({name:'keyboard_forward_reverse_owner_retention_blur_escape'});
 await page.getByRole('button',{name:'Enter full screen',exact:true}).click();await page.waitForTimeout(250);const fullscreen=await page.evaluate(()=>!!document.fullscreenElement);if(fullscreen){await page.getByRole('button',{name:'Exit full screen',exact:true}).click();await page.waitForTimeout(150);assert.equal(await page.evaluate(()=>!!document.fullscreenElement),false);}result.scenarios.push({name:'fullscreen',supported:fullscreen});
 for(const width of [390,768,1440,1971])for(const enlarged of [false,true])for(const theme of ['light','dark']){
  await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);await page.setViewportSize({width,height:1000});await page.evaluate(value=>document.documentElement.style.setProperty('--font-scale',value?'2':'1'),enlarged);await page.waitForTimeout(200);
  const controls=await graph.getByRole('group',{name:'Map controls',exact:true}).getByRole('button').evaluateAll(elements=>elements.map(el=>({name:el.getAttribute('aria-label')||el.textContent,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height})));
  assert.ok(controls.every(c=>c.width>=43.9&&c.height>=43.9));
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.equal(await graph.evaluate(el=>getComputedStyle(el).backgroundColor),await page.evaluate(()=>getComputedStyle(document.body).backgroundColor));
  await graph.scrollIntoViewIfNeeded();await page.screenshot({path:out+`/graph-${width}-${theme}-${enlarged?'2x':'1x'}.png`});
  result.scenarios.push({name:'responsive_controls_text',width,enlarged,theme,background:await graph.evaluate(el=>getComputedStyle(el).backgroundColor),rootFont:await page.evaluate(()=>getComputedStyle(document.documentElement).fontSize),controls});
 }
 const mobile=await pageFor({viewport:{width:390,height:844},hasTouch:true,isMobile:true});await mobile.goto(base);await mobile.locator('[data-atlas-node]').first().waitFor();await mobile.waitForFunction(()=>{const s=document.querySelector('[data-atlas-graph] svg[tabindex]'),r=s?.getBoundingClientRect();return r&&Math.abs(s.viewBox.baseVal.width-r.width)<1&&Math.abs(s.viewBox.baseVal.height-r.height)<1;});await mobile.locator('[data-atlas-graph]').scrollIntoViewIfNeeded();
 const mnode=mobile.locator('[data-atlas-node="part:esp32-s3"]');await mnode.tap();await mobile.waitForURL(/part=esp32-s3/);
 const msvg=mobile.locator('[data-atlas-graph] svg[tabindex="0"]'),mr=await msvg.boundingBox();const startY=await mobile.evaluate(()=>scrollY),client=await mobile.context().newCDPSession(mobile);
 await client.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:mr.x+mr.width*.5,y:mr.y+Math.min(mr.height-30,300)}]});
 for(let i=1;i<=6;i++)await client.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:mr.x+mr.width*.5,y:mr.y+Math.min(mr.height-30,300)-i*28}]});
 await client.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await mobile.waitForTimeout(300);
 const endY=await mobile.evaluate(()=>scrollY);assert.ok(endY>startY+30,'Vertical touch movement must scroll the page, not trap touch in graph');
 result.scenarios.push({name:'touch_tap_and_vertical_scroll',startY,endY,url:mobile.url()});await msvg.scrollIntoViewIfNeeded();const hr=await msvg.boundingBox(),beforePan=await mnode.boundingBox(),touchURL=mobile.url();await client.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:hr.x+hr.width*.4,y:hr.y+hr.height*.5}]});for(let i=1;i<=6;i++){await client.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:hr.x+hr.width*.4+i*16,y:hr.y+hr.height*.5}]});await mobile.waitForTimeout(20);}await client.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await mobile.waitForTimeout(150);const afterPan=await mnode.boundingBox();assert.ok(Math.abs(afterPan.x-beforePan.x)>40);assert.equal(mobile.url(),touchURL);result.scenarios.push({name:'touch_horizontal_pan_no_selection',deltaX:afterPan.x-beforePan.x});await mobile.screenshot({path:out+'/mobile-touch.png'});
 assert.deepEqual(errors,[]);assert.deepEqual(result.unexpectedRequests,[]);assert.deepEqual(fingerprint(),before);
 result.pass=true;
}catch(error){result.pass=false;result.failure=error.stack;throw error;}finally{fs.writeFileSync(out+'/result.json',JSON.stringify(result,null,2));await browser.close();console.log(JSON.stringify({pass:result.pass,buildId:result.buildId,scenarioCount:result.scenarios.length,errors:result.errors.length,unexpectedRequests:result.unexpectedRequests,outputDirectory:out,failure:result.failure},null,2));}
