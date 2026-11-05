"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import type { AtlasEdge, AtlasNode } from "@/lib/atlas-model";
import { atlasLabels, fitCamera, layoutAtlas, projectPoint, svgNumber, zoomCamera } from "@/lib/atlas-graph";
import type { GraphCamera } from "@/lib/atlas-graph";
import styles from "./AtlasGraph.module.css";

export interface AtlasGraphProps {
  nodes: AtlasNode[];
  edges: AtlasEdge[];
  selectedKey: string | null;
  onInspect: (key: string) => void;
}

const kindName = { soc: "Silicon", module: "Module", board: "Board", firmware: "Firmware" };
const statusName: Record<string, string> = { "known-good": "Known good", reported: "Reported", declared: "Declared", unverified: "Unverified", broken: "Broken" };
function Glyph({ kind }: { kind: "left" | "right" | "plus" | "minus" | "fit" | "expand" | "close" }) {
  const paths = {
    left: "M3 5v6h6M3 11a9 9 0 1 1 3 8", right: "M21 5v6h-6M21 11a9 9 0 1 0-3 8",
    plus: "M12 4v16M4 12h16", minus: "M4 12h16", fit: "M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5M9 12h6M12 9v6",
    expand: "M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5", close: "M6 6l12 12M18 6 6 18",
  };
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true"><path d={paths[kind]} /></svg>;
}

export default function AtlasGraph({ nodes, edges, selectedKey, onInspect }: AtlasGraphProps) {
  const surfaceRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const openTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hoveredNode = useRef<string | null>(null);
  const pointerFocus = useRef(false);
  const suppressClick = useRef(false);
  const drag = useRef<{ id: number; x: number; y: number; camera: GraphCamera; moved: boolean } | null>(null);
  const [camera, setCamera] = useState(fitCamera);
  const [bounds, setBounds] = useState({ width: 900, height: 650 });
  const [previewSize, setPreviewSize] = useState({ width: 268, height: 240 });
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [message, setMessage] = useState("");
  const instructionsId = useId();
  const previewTitleId = useId();
  const byKey = useMemo(() => new Map(nodes.map(node => [node.key, node])), [nodes]);
  const selected = selectedKey ? byKey.get(selectedKey) : undefined;
  const keyboardNode = selected || nodes[0];
  const preview = previewKey ? byKey.get(previewKey) : undefined;
  const geometry = useMemo(() => layoutAtlas(nodes, edges), [nodes, edges]);
  const points = useMemo(() => new Map([...geometry].map(([key, point]) => [key, projectPoint(point, camera, bounds)])), [geometry, camera, bounds]);
  const neighbors = useMemo(() => new Set(edges.filter(edge => edge.from === selectedKey || edge.to === selectedKey).flatMap(edge => [edge.from, edge.to])), [edges, selectedKey]);
  const labels = useMemo(() => atlasLabels(nodes, edges, points, selectedKey, bounds), [nodes, edges, points, selectedKey, bounds]);
  const previewEdges = preview ? edges.filter(edge => edge.from === preview.key || edge.to === preview.key) : [];
  const previewParent = preview && byKey.get(edges.find(edge => edge.kind === "lineage" && edge.to === preview.key)?.from || "");
  const selectedPair = previewEdges.find(edge => edge.kind === "recipe" && (edge.from === selectedKey || edge.to === selectedKey));
  const previewPoint = (previewKey && points.get(previewKey)) || { x: bounds.width / 2, y: bounds.height / 2 };
  const previewLeft = Math.max(8, Math.min(bounds.width - previewSize.width - 8,
    previewPoint.x + previewSize.width + 24 < bounds.width ? previewPoint.x + 18 : previewPoint.x - previewSize.width - 18));
  const previewTop = Math.max(8, Math.min(bounds.height - previewSize.height - 8, previewPoint.y - 30));
  const scale = Math.min(bounds.width, bounds.height) / 900 * camera.zoom;
  const center = { x: svgNumber(bounds.width / 2 + camera.x), y: svgNumber(bounds.height / 2 + camera.y) };

  useEffect(() => {
    const element = canvasRef.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => {
      const rect = entries[0].contentRect;
      setBounds({ width: rect.width, height: rect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!previewRef.current) return;
    const observer = new ResizeObserver(entries => {
      const rect = entries[0].target.getBoundingClientRect();
      setPreviewSize({ width: rect.width, height: rect.height });
    });
    observer.observe(previewRef.current);
    return () => observer.disconnect();
  }, [previewKey]);
  useEffect(() => {
    const changed = () => setFullscreen(document.fullscreenElement === surfaceRef.current);
    document.addEventListener("fullscreenchange", changed);
    return () => document.removeEventListener("fullscreenchange", changed);
  }, []);
  useEffect(() => {
    const outside = (event: globalThis.PointerEvent) => {
      pointerFocus.current = true;
      const target = event.target as Element;
      if (!target.closest?.("[data-atlas-node]") && !previewRef.current?.contains(target)) {
        if (openTimer.current) clearTimeout(openTimer.current);
        if (closeTimer.current) clearTimeout(closeTimer.current);
        hoveredNode.current = null;
        setPreviewKey(null);
      }
    };
    const keyboard = () => { pointerFocus.current = false; };
    const scroll = (event: Event) => {
      if (previewRef.current?.contains(event.target as Node)) return;
      if (document.activeElement === svgRef.current || previewRef.current?.contains(document.activeElement)) return;
      if (openTimer.current) clearTimeout(openTimer.current);
      hoveredNode.current = null;
      setPreviewKey(null);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", keyboard, true);
    document.addEventListener("scroll", scroll, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", keyboard, true);
      document.removeEventListener("scroll", scroll, true);
      if (closeTimer.current) clearTimeout(closeTimer.current);
      if (openTimer.current) clearTimeout(openTimer.current);
    };
  }, []);

  function cancelClose() {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    if (openTimer.current) clearTimeout(openTimer.current);
  }
  function closePreview() { cancelClose(); hoveredNode.current = null; setPreviewKey(null); }
  function scheduleClose() {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    if (openTimer.current) clearTimeout(openTimer.current);
    closeTimer.current = setTimeout(() => {
      if (hoveredNode.current || previewRef.current?.matches(":hover") || document.activeElement === svgRef.current || previewRef.current?.contains(document.activeElement)) return;
      setPreviewKey(null);
    }, 500);
  }
  function previewNode(key: string) {
    if (drag.current?.moved || previewRef.current?.contains(document.activeElement)) return;
    cancelClose(); hoveredNode.current = key;
    // Crossing another node on the way into the card must not move the card.
    if (previewKey && previewKey !== key) openTimer.current = setTimeout(() => setPreviewKey(key), 140);
    else setPreviewKey(key);
  }
  function inspect(key: string) { closePreview(); onInspect(key); }
  function changeCamera(change: (value: GraphCamera) => GraphCamera) { closePreview(); setCamera(change); }
  function rotate(delta: number) { changeCamera(value => ({ ...value, rotation: (value.rotation + delta + 360) % 360 })); }
  function fit() { changeCamera(fitCamera); }
  async function toggleFullscreen() {
    closePreview();
    try {
      if (document.fullscreenElement === surfaceRef.current) await document.exitFullscreen();
      else if (surfaceRef.current?.requestFullscreen) await surfaceRef.current.requestFullscreen();
      else setMessage("Full screen is unavailable in this browser. The map controls remain available.");
    } catch { setMessage("Full screen is unavailable in this browser. The map controls remain available."); }
  }
  function onGraphKey(event: KeyboardEvent<SVGSVGElement>) {
    if (["Enter", " "].includes(event.key) && keyboardNode) {
      event.preventDefault(); onInspect(keyboardNode.key); cancelClose(); setPreviewKey(keyboardNode.key);
    } else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      const distance = event.shiftKey ? 80 : 40;
      changeCamera(value => ({ ...value, x: value.x + (event.key === "ArrowLeft" ? -distance : event.key === "ArrowRight" ? distance : 0), y: value.y + (event.key === "ArrowUp" ? -distance : event.key === "ArrowDown" ? distance : 0) }));
    } else if (["+", "=", "-"].includes(event.key)) {
      event.preventDefault(); changeCamera(value => zoomCamera(value, value.zoom + (event.key === "-" ? -0.25 : 0.25)));
    } else if (event.key === "Home") { event.preventDefault(); fit(); }
    else if (["[", "]"].includes(event.key)) { event.preventDefault(); rotate(event.key === "[" ? -30 : 30); }
    else if (event.key === "Escape") closePreview();
  }
  function pointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, camera, moved: false };
  }
  function pointerMove(event: PointerEvent<SVGSVGElement>) {
    const current = drag.current;
    if (!current || current.id !== event.pointerId) return;
    const x = event.clientX - current.x, y = event.clientY - current.y;
    if (!current.moved) {
      if (Math.hypot(x, y) < 6) return;
      if (event.pointerType === "touch" && Math.abs(y) > Math.abs(x)) return;
      current.moved = true; suppressClick.current = true; closePreview();
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    setCamera({ ...current.camera, x: current.camera.x + x, y: current.camera.y + y });
  }
  function pointerUp(event: PointerEvent<SVGSVGElement>) {
    if (drag.current?.id !== event.pointerId) return;
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    setTimeout(() => { suppressClick.current = false; }, 0);
  }

  return <div ref={surfaceRef} className={styles.surface} data-atlas-graph>
    <div className={styles.toolbar} role="group" aria-label="Map controls">
      <div className={styles.controlGroup}>
        <button type="button" onClick={() => rotate(-30)} aria-label="Rotate map counterclockwise" title="Rotate counterclockwise"><Glyph kind="left" /></button>
        <output aria-label="Map rotation">{camera.rotation}°</output>
        <button type="button" onClick={() => rotate(30)} aria-label="Rotate map clockwise" title="Rotate clockwise"><Glyph kind="right" /></button>
      </div>
      <div className={styles.controlGroup}>
        <button type="button" onClick={() => changeCamera(value => zoomCamera(value, value.zoom - 0.25))} disabled={camera.zoom === 1} aria-label="Zoom map out"><Glyph kind="minus" /></button>
        <output aria-label="Map zoom">{Math.round(camera.zoom * 100)}%</output>
        <button type="button" onClick={() => changeCamera(value => zoomCamera(value, value.zoom + 0.25))} disabled={camera.zoom === 3} aria-label="Zoom map in"><Glyph kind="plus" /></button>
      </div>
      <button type="button" className={styles.fit} onClick={fit}><Glyph kind="fit" /><span>Fit</span></button>
      <button type="button" onClick={toggleFullscreen} aria-label={fullscreen ? "Exit full screen" : "Enter full screen"} title={fullscreen ? "Exit full screen" : "Full screen"}><Glyph kind="expand" /></button>
    </div>
    <div ref={canvasRef} className={styles.canvas}>
      {nodes.length ? <svg ref={svgRef} className={styles.diagram} width="100%" height="100%" viewBox={`0 0 ${bounds.width} ${bounds.height}`} role="group" tabIndex={0}
        aria-label={`Relationship map. ${selected ? selected.name + " selected." : "Choose a record to inspect."}`} aria-describedby={instructionsId}
        onFocus={() => { if (keyboardNode && !drag.current && !pointerFocus.current) { cancelClose(); setPreviewKey(keyboardNode.key); } }} onBlur={scheduleClose} onKeyDown={onGraphKey}
        onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerUp}>
        <g className={styles.guides} aria-hidden="true">
          {[215, 294, 372, 400].map(radius => <circle key={radius} cx={center.x} cy={center.y} r={svgNumber(radius * scale)} />)}
          {Array.from({ length: 72 }, (_, i) => {
            const angle = i / 72 * Math.PI * 2 + camera.rotation * Math.PI / 180;
            return <line key={i} x1={svgNumber(center.x + 417 * scale * Math.cos(angle))} y1={svgNumber(center.y + 417 * scale * Math.sin(angle))} x2={svgNumber(center.x + (i % 6 ? 421 : 429) * scale * Math.cos(angle))} y2={svgNumber(center.y + (i % 6 ? 421 : 429) * scale * Math.sin(angle))} />;
          })}
        </g>
        <g aria-hidden="true" className={styles.edges}>{edges.map(edge => {
          const a = points.get(edge.from), b = points.get(edge.to); if (!a || !b) return null;
          const active = edge.from === selectedKey || edge.to === selectedKey;
          const hovered = edge.from === previewKey || edge.to === previewKey;
          const status = edge.recipe?.status;
          return <path key={edge.key} data-kind={edge.kind} data-status={status} data-active={active || undefined} data-hovered={hovered || undefined}
            d={`M${a.x},${a.y} Q${svgNumber(center.x + ((a.x + b.x) / 2 - center.x) * .65)},${svgNumber(center.y + ((a.y + b.y) / 2 - center.y) * .65)} ${b.x},${b.y}`} />;
        })}</g>
        <g aria-hidden="true" className={styles.centerMark} transform={`translate(${center.x},${center.y})`}>
          <path d="M-58 -40h-12v12M58 -40h12v12M-58 40h-12V28M58 40h12V28" />
          <text y="-8">ESP / ATLAS</text><text y="15" className={styles.centerSub}>FOLLOW THE EVIDENCE</text>
        </g>
        {nodes.map(node => {
          const point = points.get(node.key); if (!point) return null;
          const active = node.key === selectedKey, connected = neighbors.has(node.key), radius = active ? 6 : node.kind === "soc" ? 4.5 : connected ? 3.6 : 2.7;
          return <g key={node.key} className={styles.node} data-atlas-node={node.key} data-kind={node.kind} data-active={active || undefined} data-connected={connected || undefined} data-hovered={node.key === previewKey || undefined}
            aria-hidden="true" onPointerEnter={event => { if (event.pointerType !== "touch") previewNode(node.key); }}
            onPointerLeave={() => { hoveredNode.current = null; scheduleClose(); }}
            onClick={event => { if (suppressClick.current) { event.preventDefault(); return; } inspect(node.key); }}>
            <circle className={styles.hit} cx={point.x} cy={point.y} r="11" />
            {node.kind === "soc" ? <circle cx={point.x} cy={point.y} r={radius} /> : node.kind === "firmware" ? <path d={`M${point.x},${svgNumber(point.y - radius)}l${radius},${radius} -${radius},${radius} -${radius},-${radius}Z`} /> : <rect x={svgNumber(point.x - radius)} y={svgNumber(point.y - radius)} width={svgNumber(radius * 2)} height={svgNumber(radius * 2)} />}
            {active && <circle className={styles.selectionRing} cx={point.x} cy={point.y} r="11" />}
          </g>;
        })}
        <g className={styles.labels} aria-hidden="true">{labels.map(label => <text key={label.key} x={label.x} y={label.y} dominantBaseline="middle" data-active={label.key === selectedKey || undefined}>{label.text}</text>)}</g>
      </svg> : <p className={styles.empty}>No records are available for this map. Catalog navigation remains available.</p>}
      {preview && <div ref={previewRef} className={styles.preview} role="region" aria-labelledby={previewTitleId} style={{ left: previewLeft, top: previewTop }}
        onPointerEnter={cancelClose} onPointerLeave={scheduleClose} onFocusCapture={cancelClose} onBlurCapture={scheduleClose}
        onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); svgRef.current?.focus({ preventScroll: true }); closePreview(); } }}>
        <button type="button" className={styles.dismiss} aria-label="Close record preview" onClick={() => { svgRef.current?.focus({ preventScroll: true }); closePreview(); }}><Glyph kind="close" /></button>
        <span className={styles.eyebrow}>{kindName[preview.kind]}</span><strong id={previewTitleId}>{preview.name}</strong>
        <span className={styles.recordId}>{preview.id}</span>
        {previewParent && <p>Built on {previewParent.name}</p>}
        <p>{previewEdges.length} recorded relationship{previewEdges.length === 1 ? "" : "s"} in this map.</p>
        {selectedPair?.recipe && <p className={styles.trust}>Recipe evidence: {statusName[selectedPair.recipe.status] || selectedPair.recipe.status}</p>}
        <button type="button" className={styles.inspect} onClick={() => { inspect(preview.key); svgRef.current?.focus({ preventScroll: true }); closePreview(); }}>Inspect record <span aria-hidden="true">↗</span></button>
      </div>}
      <div className={styles.readout} aria-hidden="true"><span>{nodes.length} records</span><span>{edges.length} relationships</span></div>
    </div>
    <div className={styles.legend}><span><i data-kind="soc" />Silicon</span><span><i data-kind="board" />Hardware</span><span><i data-kind="firmware" />Firmware</span><span>Orange: selected connections</span></div>
    <p id={instructionsId} className={styles.instructions}>Drag to pan. Use the record selector to explore every node. Keyboard: arrows move, + / − zoom, [ / ] rotate, Home fits, Enter inspects. Lines show recorded relationships, not wiring or a compatibility guarantee.</p>
    {message && <p className={styles.message} role="status">{message}</p>}
  </div>;
}
