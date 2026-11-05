"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import TrackedLink from "@/components/TrackedLink";
import TrustTierBadge from "@/components/TrustTierBadge";
import { API_BASE, type SourceEntry, type Recipe } from "@/lib/api";
import type { AtlasCatalog, AtlasNode } from "@/lib/atlas-model";
import { atlasPartDetail, type AtlasPartDetail } from "@/lib/atlas-detail";
import { recipeSourceHref, sourceHref } from "@/lib/atlas-route";
import { tierClaim, recipeCaveat } from "@/lib/flash-copy";
import { viewSourceUrl } from "@/lib/github";
import styles from "./AtlasExplorer.module.css";

export function AtlasSources({ sources, recipe }: { sources: SourceEntry[]; recipe?: Recipe }) {
  if (!sources.length) return <p className={styles.muted}>No citation recorded.</p>;
  return <ul className={styles.sources}>{sources.map((source, i) => {
    const recordedHref = sourceHref(source.url);
    const href = recipe ? recipeSourceHref(recipe, source) : recordedHref;
    const withheldArtifact = recordedHref && !href;
    return <li key={`${source.field}:${source.url}:${i}`}>
      <span>{source.field === "*" ? "Whole record" : source.field}</span>
      {href ? <TrackedLink href={href} linkType="source" title={href}>{new URL(href).hostname} ↗</TrackedLink> : withheldArtifact ? <>
        <span>{source.url}</span>
        <small>Artifact citation retained. Download disabled for this broken recipe.</small>
      </> : <span>Source link unavailable</span>}
      <small>{source.verified ? `Verified ${source.verified}` : "Verification date not recorded"}</small>
    </li>;
  })}</ul>;
}

export function AtlasRecipe({ recipe, catalog }: { recipe: Recipe; catalog: AtlasCatalog }) {
  const board = catalog.parts.find(part => part.id === recipe.board);
  const firmware = catalog.firmware.find(fw => fw.id === recipe.firmware);
  const caveat = recipeCaveat(recipe);
  return <section className={styles.recipe} data-atlas-recipe={recipe.id}>
    <p className={styles.eyebrow}>Exact recipe / {recipe.id}</p>
    <h3>{board?.name ?? recipe.board} <span aria-hidden="true">×</span> {firmware?.name ?? recipe.firmware}</h3>
    <TrustTierBadge status={recipe.status} />
    <p>{tierClaim(recipe.status, board?.name ?? recipe.board)}</p>
    {caveat ? <p className={styles.caveat}>{caveat}</p> : null}
    {recipe.verified_at ? <p className={styles.muted}>Verification recorded {recipe.verified_at}{recipe.verified_by ? ` by ${recipe.verified_by}` : ""}.</p> : null}
    {recipe.firmware_version ? <p>Recorded version: <code>{recipe.firmware_version}</code></p> : null}
    {recipe.status === "broken" ? <p className={styles.notice}>Installation is unavailable for this broken pairing. Its cited history remains here.</p> : !recipe.flash ? <p className={styles.notice}>No installation artifact is recorded for this pairing.</p> : <p className={styles.muted}>Installation requirements and actions belong to the firmware record. A recipe tier is not a guarantee.</p>}
    <AtlasSources sources={recipe.sources} recipe={recipe} />
    <TrackedLink href={viewSourceUrl(`data/recipes/${encodeURIComponent(recipe.id)}/recipe.md`)} linkType="github_view">Read the recipe record ↗</TrackedLink>
  </section>;
}

type DetailState = { status: "loading" } | { status: "ok"; detail: AtlasPartDetail } | { status: "error" | "not_found" };

function PartContext({ node, onInspect }: { node: AtlasNode; onInspect: (key: string) => void }) {
  const [state, setState] = useState<DetailState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(`${API_BASE}/parts/${encodeURIComponent(node.id)}`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(12000)]) });
        if (controller.signal.aborted) return;
        if (!response.ok) { setState({ status: response.status === 404 ? "not_found" : "error" }); return; }
        const detail = atlasPartDetail(await response.json(), node.id);
        if (!detail) throw new Error("Invalid part detail");
        if (!controller.signal.aborted) setState({ status: "ok", detail });
      } catch { if (!controller.signal.aborted) setState({ status: "error" }); }
    }
    void load();
    return () => controller.abort();
  }, [node.id, attempt]);
  if (state.status === "loading") return <p role="status">Loading the source record…</p>;
  if (state.status !== "ok") return <div role="status"><p>{state.status === "not_found" ? "This record is no longer available at the API." : "The detail request failed. The catalog selection is still here."}</p><button className="btn" type="button" onClick={() => { setState({ status: "loading" }); setAttempt(value => value + 1); }}>Retry details</button></div>;
  const parents = [state.detail.chain.soc, state.detail.chain.module].filter(part => part && part.id !== node.id);
  return <>
    {parents.length ? <div className={styles.lineage}><p className={styles.eyebrow}>Hardware lineage</p>{parents.map(part => part ? <button type="button" key={part.id} onClick={() => onInspect(`part:${part.id}`)}>{part.name} <span aria-hidden="true">↗</span></button> : null)}<p className={styles.muted}>Inherited specifications belong to these source records.</p></div> : null}
    {state.detail.body ? <details className={styles.recordNotes}><summary>Notes from the part record</summary><p>{state.detail.body}</p></details> : null}
    <AtlasSources sources={state.detail.sources} />
  </>;
}

export default function AtlasInspector({ node, catalog, onInspect, onRecipe }: { node: AtlasNode | null; catalog: AtlasCatalog; onInspect: (key: string) => void; onRecipe: (recipe: Recipe) => void }) {
  const [limit, setLimit] = useState(12);
  if (!node) return <div className={styles.inspector}><h2>Choose a record.</h2><p>Select a point on the map or use the record picker. Its sources and recorded connections appear here.</p></div>;
  const recipes = catalog.recipes.filter(recipe => node.kind === "firmware" ? recipe.firmware === node.id : recipe.board === node.id);
  const popularity = node.firmware?.popularity;
  const popularitySources = node.firmware?.sources.filter(source => source.field === "popularity" || source.field === "*") ?? [];
  return <div className={styles.inspector}>
    <p className={styles.eyebrow}>Selected {node.kind === "soc" ? "silicon" : node.kind}</p>
    <h2>{node.name}</h2>
    <p className={styles.recordId}>{node.id}</p>
    <Link className={styles.recordLink} href={`/${node.kind === "firmware" ? "firmware" : "parts"}/${encodeURIComponent(node.id)}`}>Open the full record <span aria-hidden="true">↗</span></Link>
    {node.part ? <PartContext key={node.key} node={node} onInspect={onInspect} /> : null}
    {node.firmware ? <>
      {node.firmware.summary ? <p>{node.firmware.summary}</p> : null}
      <p className={styles.muted}>Category: {node.firmware.category || "Not recorded"}</p>
      {popularity && popularity.as_of && popularitySources.length ? <section className={styles.popularity}>
        <p className={styles.eyebrow}>Repository signals / observed {popularity.as_of}</p>
        <div>{typeof popularity.stars === "number" ? <span><b>{popularity.stars.toLocaleString("en-US")}</b> stars</span> : null}{typeof popularity.forks === "number" ? <span><b>{popularity.forks.toLocaleString("en-US")}</b> forks</span> : null}</div>
        <p className={styles.muted}>Popularity measures attention, not compatibility.</p>
        <AtlasSources sources={popularitySources} />
      </section> : null}
      <AtlasSources sources={node.firmware.sources} />
    </> : null}
    <section className={styles.relationships}>
      <h3>{recipes.length} recorded {recipes.length === 1 ? "recipe" : "recipes"}</h3>
      <p className={styles.muted}>Each pairing retains its own evidence. Missing recipes do not mean incompatibility.</p>
      {recipes.slice(0, limit).map(recipe => <button type="button" key={recipe.id} onClick={() => onRecipe(recipe)} className={styles.relationship}>
        <span>{node.kind === "firmware" ? catalog.parts.find(part => part.id === recipe.board)?.name ?? recipe.board : catalog.firmware.find(fw => fw.id === recipe.firmware)?.name ?? recipe.firmware}</span><TrustTierBadge status={recipe.status} /><span aria-hidden="true">↗</span>
      </button>)}
      {recipes.length > limit ? <button type="button" className="btn" onClick={() => setLimit(value => value + 20)}>Show more recipes ({recipes.length - limit} remaining)</button> : null}
    </section>
  </div>;
}
