"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import TrustTierBadge from "@/components/TrustTierBadge";
import type { Recipe } from "@/lib/api";
import { buildAtlasModel, exactRecipe, type AtlasCatalog } from "@/lib/atlas-model";
import { ATLAS_LENSES, atlasHref, atlasLens, type AtlasLens } from "@/lib/atlas-route";
import AtlasGraph from "./AtlasGraph";
import AtlasInspector, { AtlasRecipe, AtlasSources } from "./AtlasInspector";
import styles from "./AtlasExplorer.module.css";

const LENS_COPY: Record<AtlasLens, { name: string; title: string; description: string }> = {
  map: { name: "Map", title: "Follow the connections.", description: "Silicon, boards and firmware. Select a record to see where the evidence leads." },
  silicon: { name: "Silicon", title: "Start at the source.", description: "Explore the chips behind the hardware. Specifications stay with their originating records." },
  hardware: { name: "Hardware", title: "Find your hardware.", description: "Every module and board in the catalog, connected to its recorded lineage." },
  firmware: { name: "Firmware", title: "Discover what’s recorded.", description: "Firmware projects, their cited recipes and the evidence for each exact board." },
  projects: { name: "Projects", title: "From an idea to a board.", description: "Use the project finder and spec wizard to explore requirements against the catalog." },
  evidence: { name: "Evidence", title: "A map with a paper trail.", description: "Inspect the sources, notes and trust tier behind an exact relationship." },
};

export default function AtlasExplorer({ catalog }: { catalog: AtlasCatalog }) {
  const model = useMemo(() => buildAtlasModel(catalog), [catalog]);
  const params = useSearchParams();
  const [pending, startTransition] = useTransition();
  const [lookup, setLookup] = useState("");
  const query = params.toString();
  const lens = atlasLens(params.get("lens"));
  const partId = params.get("part");
  const firmwareId = params.get("firmware");
  const recipeId = params.get("recipe");
  const part = catalog.parts.find(record => record.id === partId);
  const firmware = catalog.firmware.find(record => record.id === firmwareId);
  const defaultNode = model.nodes.find(node => node.key === "part:esp32-s3") ?? model.nodes[0] ?? null;
  const requestedKey = params.get("focus") === "firmware" && firmwareId ? `firmware:${firmwareId}` : partId ? `part:${partId}` : firmwareId ? `firmware:${firmwareId}` : null;
  const node = requestedKey ? model.nodes.find(record => record.key === requestedKey) ?? null : defaultNode;
  const recipe = recipeId && partId && firmwareId ? exactRecipe(catalog, recipeId, partId, firmwareId) : null;
  const badSelection = Boolean(partId && !part || firmwareId && !firmware || recipeId && !recipe);
  const pair = part && firmware ? catalog.recipes.filter(record => record.board === part.id && record.firmware === firmware.id) : [];
  const allLensNodes = model.nodes.filter(record => lens === "silicon" ? record.kind === "soc" : lens === "hardware" ? record.kind === "board" || record.kind === "module" : lens === "firmware" ? record.kind === "firmware" : true);
  const lensNodes = lookup.trim() ? allLensNodes.filter(record => `${record.name} ${record.id}`.toLowerCase().includes(lookup.trim().toLowerCase())) : allLensNodes;

  // Next integrates native history with useSearchParams. Selection is local
  // view state: keep Back/share links without refetching the entire catalog.
  function navigate(patch: Record<string, string | null>) { startTransition(() => window.history.pushState(null, "", atlasHref(query, patch))); }
  function inspect(key: string) {
    const selected = model.nodes.find(record => record.key === key);
    if (!selected) return;
    navigate(selected.kind === "firmware" ? { firmware: selected.id, focus: "firmware", recipe: null } : { part: selected.id, focus: "part", recipe: null });
  }
  function inspectRecipe(selected: Recipe) { navigate({ part: selected.board, firmware: selected.firmware, recipe: selected.id, lens: "evidence", focus: "firmware" }); }

  return <div className={styles.explorer}>
    <header className={styles.intro}>
      <div><p className={styles.eyebrow}>ESP / Atlas</p><h1>The ESP32 world.<br /><span>Mapped.</span></h1></div>
      <div className={styles.introAside}><p>A living index of hardware and software.<br />Follow a connection. Inspect its evidence.</p><dl className={styles.totals}><div><dt>Parts</dt><dd>{catalog.parts.length}</dd></div><div><dt>Firmware</dt><dd>{catalog.firmware.length}</dd></div><div><dt>Recipes</dt><dd>{catalog.recipes.length}</dd></div></dl><p className={styles.muted}>Counts from the loaded catalog. Recipe totals include every trust tier.</p></div>
    </header>
    <nav className={styles.lenses} aria-label="Atlas lenses">{ATLAS_LENSES.map((item, index) => <Link key={item} href={atlasHref(query, { lens: item })} prefetch={false} scroll={false} onNavigate={event => { event.preventDefault(); navigate({ lens: item }); }} aria-current={lens === item ? "page" : undefined}><small aria-hidden="true">0{index + 1}</small>{LENS_COPY[item].name}<span aria-hidden="true">↗</span></Link>)}</nav>
    <div className={styles.context} aria-label="Selected context">
      <span>{part?.name ?? (partId ? `Unknown part: ${partId}` : "No hardware selected")}</span><span aria-hidden="true">×</span><span>{firmware?.name ?? (firmwareId ? `Unknown firmware: ${firmwareId}` : "No firmware selected")}</span>
      {recipe ? <TrustTierBadge status={recipe.status} /> : null}
      {params.get("goal") ? <span>Goal: {params.get("goal")}</span> : null}
      <button type="button" onClick={() => navigate({ part: null, firmware: null, recipe: null, focus: null })}>Clear selection</button>
      <span role="status" className={styles.pending}>{pending ? "Opening…" : ""}</span>
    </div>
    {badSelection ? <div className={styles.notice} role="status">This URL does not resolve to a matching record or exact recipe. The requested IDs remain in the address bar; choose a record or clear the selection.</div> : null}
    {model.gaps.length ? <details className={styles.gaps}><summary>{model.gaps.length} catalog references could not be mapped</summary><p>Unresolved references are kept out of the drawing; they are not invented connections.</p><ul>{model.gaps.map((gap, i) => <li key={i}>{gap.message}</li>)}</ul></details> : null}
    <div className={styles.workspaceHeading}><div><h2>{LENS_COPY[lens].title}</h2><p>{LENS_COPY[lens].description}</p></div><Link href="/wizard" className={styles.searchLink}>Search &amp; filter all parts ↗</Link></div>
    {!model.nodes.length ? <div className={styles.unavailable}><h2>No records returned.</h2><p>The catalog request succeeded, but these collections are empty.</p></div> : <div className={styles.workspace}>
      <section className={styles.canvasArea} aria-label={LENS_COPY[lens].name}>
        {lens === "map" ? <AtlasGraph nodes={model.nodes} edges={model.edges} selectedKey={node?.key ?? null} onInspect={inspect} /> : null}
        {["silicon", "hardware", "firmware"].includes(lens) ? <>
          <div className={styles.collectionHeader}><label htmlFor="atlas-name-filter">Find a name in this view<input id="atlas-name-filter" type="search" value={lookup} onChange={event => setLookup(event.target.value)} placeholder="Name or record ID…" /></label><span>{lensNodes.length} of {allLensNodes.length} records</span></div>
          <div className={styles.collection}>{lensNodes.map(record => {
            const count = catalog.recipes.filter(row => record.kind === "firmware" ? row.firmware === record.id : row.board === record.id).length;
            return <button type="button" className={styles.collectionRow} key={record.key} onClick={() => inspect(record.key)} aria-pressed={node?.key === record.key}><span className={styles.eyebrow}>{record.kind === "soc" ? "Silicon" : record.kind}</span><strong>{record.name}</strong><span>{count ? `${count} recorded ${count === 1 ? "recipe" : "recipes"}` : "Inspect record"}</span><span aria-hidden="true">↗</span></button>;
          })}</div>
          {!lensNodes.length ? <p className={styles.notice}>No name matches in this view. Use catalog search for aliases and ranked results.</p> : null}
        </> : null}
        {lens === "projects" ? <div className={styles.projects}>
          <span className={styles.projectMark} aria-hidden="true">✳</span><h3>What do you want<br />to build?</h3><p>Explore an idea with the project finder, or specify radio, memory, USB and form-factor needs in the wizard. Recommendations and ranking come from the existing catalog services.</p>
          <div className={styles.projectChoices}><Link href="/">Describe a project <span aria-hidden="true">↗</span></Link><Link href="/wizard">Choose capabilities <span aria-hidden="true">↗</span></Link></div>
          <form action="/wizard" method="get" className={styles.keywordSearch}><label htmlFor="atlas-keyword">Already know a name, model or alias?</label><div><input id="atlas-keyword" name="q" type="search" placeholder="e.g. es3c28p" required /><button type="submit" className="btn btn--primary">Search parts ↗</button></div></form>
          <p className={styles.muted}>The finder and wizard open their existing workspaces. Your atlas selection remains in this page’s URL for Back.</p>
        </div> : null}
        {lens === "evidence" ? <div className={styles.evidence}>
          {recipe ? <AtlasRecipe recipe={recipe} catalog={catalog} /> : <>
            <p className={styles.eyebrow}>Evidence / exact relationships</p><h3>{part && firmware ? `${part.name} × ${firmware.name}` : "Choose a relationship to inspect."}</h3>
            {part && firmware ? <><p>{pair.length ? `${pair.length} exact recipe records for this pair.` : "No recipe is recorded for this exact pair. That is an evidence gap, not an incompatibility claim."}</p>{pair.map(row => <button className={styles.relationship} type="button" key={row.id} onClick={() => inspectRecipe(row)}><span>{row.id}</span><TrustTierBadge status={row.status} /><span aria-hidden="true">↗</span></button>)}</> : <p>Select a board or firmware, then choose a recorded recipe in the inspector. Every recipe keeps its own status, notes and citations.</p>}
            {node ? <section><h4>Sources for {node.name}</h4><AtlasSources sources={node.part?.sources ?? node.firmware?.sources ?? []} /></section> : null}
          </>}
          <details className={styles.trustGuide}><summary>How to read the evidence</summary><dl><dt>Known good</dt><dd>Cited for this exact board; actual hardware flashing only where the notes say so.</dd><dt>Reported</dt><dd>Community-submitted and cited, not independently verified.</dd><dt>Declared</dt><dd>The project names this board; no flashable build confirmed yet.</dd><dt>Unverified</dt><dd>A cited lead, not confirmed support.</dd><dt>Broken</dt><dd>Known incompatible or regressed. Installation is unavailable.</dd></dl><p>Unknown future statuses remain visible as recorded. Shared silicon alone never establishes a recipe.</p></details>
        </div> : null}
      </section>
      <aside className={styles.sidebar} aria-label="Record inspector">
        <div className={styles.picker}><label htmlFor="atlas-record">Inspect a record<select id="atlas-record" aria-label="Inspect a record" value={node?.key ?? ""} onChange={event => inspect(event.target.value)}><option value="" disabled>Choose a record</option>{["soc", "module", "board", "firmware"].map(kind => <optgroup key={kind} label={kind === "soc" ? "Silicon" : kind}>{model.nodes.filter(record => record.kind === kind).map(record => <option key={record.key} value={record.key}>{record.name}</option>)}</optgroup>)}</select></label></div>
        <AtlasInspector key={node?.key ?? "empty"} node={node} catalog={catalog} onInspect={inspect} onRecipe={inspectRecipe} />
      </aside>
    </div>}
    <div className={styles.endnote}><span>Every line is a recorded relationship.</span><span>Shared silicon does not establish compatibility.</span><Link href="/how-we-work">How the atlas is maintained ↗</Link></div>
  </div>;
}
