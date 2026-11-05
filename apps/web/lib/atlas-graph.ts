// Presentation geometry only. Edges are supplied by the API read model;
// distance and placement do not express compatibility or electrical wiring.
export interface GraphPoint { x: number; y: number }
export interface GraphCamera { zoom: number; rotation: number; x: number; y: number }
export interface GraphBounds { width: number; height: number }
type LayoutNode = { key: string; kind: string; name: string };
type LayoutEdge = { from: string; to: string; kind: string };

// Node and browsers can differ in the final bit of trigonometric results.
// Serialize a shared precision so SSR and hydration draw identical attributes.
export const svgNumber = (value: number): number => Math.round(value * 1000) / 1000 || 0;

export const fitCamera = (): GraphCamera => ({ zoom: 1, rotation: 0, x: 0, y: 0 });
export function zoomCamera(camera: GraphCamera, requested: number): GraphCamera {
  const zoom = Math.max(1, Math.min(3, requested));
  return { ...camera, zoom, x: camera.x * zoom / camera.zoom, y: camera.y * zoom / camera.zoom };
}
export function projectPoint(point: GraphPoint, camera: GraphCamera, bounds: GraphBounds): GraphPoint {
  const turn = camera.rotation * Math.PI / 180;
  const scale = Math.min(bounds.width, bounds.height) / 900 * camera.zoom;
  return {
    x: svgNumber(bounds.width / 2 + (point.x * Math.cos(turn) - point.y * Math.sin(turn)) * scale + camera.x),
    y: svgNumber(bounds.height / 2 + (point.x * Math.sin(turn) + point.y * Math.cos(turn)) * scale + camera.y),
  };
}

export function layoutAtlas(nodes: readonly LayoutNode[], edges: readonly LayoutEdge[]): Map<string, GraphPoint> {
  const ordered = [...nodes].sort((a, b) => a.key.localeCompare(b.key));
  const byKey = new Map(ordered.map(node => [node.key, node]));
  const parents = new Map(edges.filter(edge => edge.kind === "lineage").map(edge => [edge.to, edge.from]));
  const root = (key: string) => {
    const seen = new Set<string>();
    while (parents.has(key) && byKey.has(parents.get(key)!) && !seen.has(key)) {
      seen.add(key); key = parents.get(key)!;
    }
    return key;
  };
  const result = new Map<string, GraphPoint>();
  const place = (key: string, radius: number, angle: number) => result.set(key, { x: svgNumber(radius * Math.cos(angle)), y: svgNumber(radius * Math.sin(angle)) });
  const chips = ordered.filter(node => node.kind === "soc");
  chips.forEach((chip, index) => {
    const angle = index / chips.length * Math.PI * 2 - Math.PI / 2;
    const spread = Math.min(0.45, Math.PI * 1.5 / chips.length);
    place(chip.key, 215, angle);
    const children = ordered.filter(node => node.kind !== "firmware" && node.key !== chip.key && root(node.key) === chip.key);
    const modules = children.filter(node => node.kind === "module");
    modules.forEach((node, i) => place(node.key, 258, angle + (i - (modules.length - 1) / 2) * Math.min(0.1, spread / Math.max(1, modules.length))));
    const boards = children.filter(node => node.kind === "board");
    const columns = Math.min(10, boards.length), rows = Math.ceil(boards.length / Math.max(1, columns));
    boards.forEach((node, i) => {
      const row = Math.floor(i / columns), count = Math.min(columns, boards.length - row * columns);
      place(node.key, 294 + row * 60 / Math.max(1, rows - 1), angle + (i % columns - (count - 1) / 2) * spread / Math.max(1, columns));
    });
  });
  const unplaced = ordered.filter(node => node.kind !== "firmware" && !result.has(node.key));
  unplaced.forEach((node, i) => place(node.key, 372, i / unplaced.length * Math.PI * 2));
  const firmware = ordered.filter(node => node.kind === "firmware");
  firmware.forEach((node, i) => place(node.key, 400, i / firmware.length * Math.PI * 2 - Math.PI / 2));
  return result;
}

export interface GraphLabel extends GraphPoint {
  key: string; text: string; left: number; right: number; top: number; bottom: number;
}
export function atlasLabels(nodes: readonly LayoutNode[], edges: readonly LayoutEdge[], points: Map<string, GraphPoint>, selectedKey: string | null, bounds: GraphBounds, fontSize = 12): GraphLabel[] {
  const nearby = new Set(edges.filter(edge => edge.from === selectedKey || edge.to === selectedKey).flatMap(edge => [edge.from, edge.to]));
  const compact = bounds.width < 600;
  const chips = nodes.filter(node => node.kind === "soc").filter((_, i) => !compact || i % 2 === 0);
  const neighbors = compact ? [] : nodes.filter(node => nearby.has(node.key) && node.kind !== "soc").slice(0, 5);
  const candidates = [nodes.find(node => node.key === selectedKey), ...chips, ...neighbors].filter((node): node is LayoutNode => !!node);
  const labels: GraphLabel[] = [], seen = new Set<string>();
  for (const node of candidates) {
    if (seen.has(node.key)) continue;
    seen.add(node.key);
    const point = points.get(node.key);
    if (!point || point.x < 0 || point.x > bounds.width || point.y < 0 || point.y > bounds.height) continue;
    const maxChars = compact ? 22 : 30;
    const text = node.name.length > maxChars ? node.name.slice(0, maxChars - 1) + "…" : node.name;
    const width = text.length * fontSize * 0.64;
    const x = Math.max(10, Math.min(bounds.width - width - 10, point.x + (point.x < bounds.width / 2 ? 12 : -width - 12)));
    for (const offset of [0, -20, 20, -40, 40, -60, 60]) {
      const y = Math.max(fontSize + 10, Math.min(bounds.height - fontSize - 34, point.y + offset));
      const box = { left: x, right: x + width, top: y - fontSize * 0.6, bottom: y + fontSize * 0.6 };
      if (labels.some(other => box.left < other.right + 6 && box.right > other.left - 6 && box.top < other.bottom + 4 && box.bottom > other.top - 4)) continue;
      labels.push({ key: node.key, text, x: svgNumber(x), y: svgNumber(y), ...box }); break;
    }
  }
  return labels;
}
