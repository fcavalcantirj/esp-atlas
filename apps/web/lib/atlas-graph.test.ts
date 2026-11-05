import assert from "node:assert/strict";
import test from "node:test";
import { atlasLabels, fitCamera, layoutAtlas, projectPoint, svgNumber, zoomCamera } from "./atlas-graph.ts";

test("Every supplied node is placed once, including disconnected and cyclic records", () => {
  const nodes = [
    { key: "part:s", kind: "soc", name: "Chip" },
    { key: "part:m", kind: "module", name: "Module" },
    { key: "part:b", kind: "board", name: "Board" },
    { key: "firmware:b", kind: "firmware", name: "Firmware" },
    { key: "part:orphan", kind: "board", name: "Orphan" },
    { key: "part:cycle", kind: "module", name: "Cycle" },
  ] as const;
  const edges = [
    { from: "part:s", to: "part:m", kind: "lineage" },
    { from: "part:m", to: "part:b", kind: "lineage" },
    { from: "part:b", to: "firmware:b", kind: "recipe" },
    { from: "part:cycle", to: "part:cycle", kind: "lineage" },
  ] as const;
  const points = layoutAtlas(nodes, edges);
  assert.equal(points.size, nodes.length);
  for (const node of nodes) {
    const point = points.get(node.key)!;
    assert.ok(Number.isFinite(point.x) && Number.isFinite(point.y));
    assert.ok(Math.hypot(point.x, point.y) <= 400.001);
  }
  assert.notDeepEqual(points.get("part:b"), points.get("firmware:b"));
  assert.deepEqual(layoutAtlas([...nodes].reverse(), edges), points);
});

test("Serialized graph coordinates have shared precision across server and browser trig implementations", () => {
  assert.equal(svgNumber(377.29704284069066), svgNumber(377.2970428406906));
  assert.equal(svgNumber(377.29704284069066), 377.297);
  assert.equal(Object.is(svgNumber(-0.00001), -0), false);
  const points = layoutAtlas(Array.from({ length: 17 }, (_, i) => ({ key: String(i), kind: "soc", name: String(i) })), []);
  for (const point of points.values()) {
    const projected = projectPoint(point, { zoom: 1.75, rotation: 150, x: 12.33333, y: -40.88888 }, { width: 1440, height: 777 });
    for (const coordinate of [point.x, point.y, projected.x, projected.y]) assert.equal(coordinate, svgNumber(coordinate));
  }
});

test("Rotation returns to its original position; zoom retains the viewed world center; Fit resets only camera", () => {
  const point = { x: 200, y: -30 };
  const bounds = { width: 1200, height: 700 };
  const initial = { zoom: 1, rotation: 0, x: 80, y: -50 };
  const rotated = projectPoint(point, { ...initial, rotation: 360 }, bounds);
  const start = projectPoint(point, initial, bounds);
  assert.ok(Math.abs(rotated.x - start.x) < 0.00001);
  assert.ok(Math.abs(rotated.y - start.y) < 0.00001);
  const zoomed = zoomCamera(initial, 2);
  assert.equal(zoomed.x / zoomed.zoom, initial.x / initial.zoom);
  assert.equal(zoomed.y / zoomed.zoom, initial.y / initial.zoom);
  assert.equal(zoomCamera(initial, 100).zoom, 3);
  assert.equal(zoomCamera(initial, 0).zoom, 1);
  assert.deepEqual(fitCamera(), { zoom: 1, rotation: 0, x: 0, y: 0 });
});

test("A densely connected selection keeps sparse, contained, nonoverlapping labels at phone and wide sizes", () => {
  const nodes = [
    { key: "part:s", kind: "soc", name: "ESP32-S3" },
    ...Array.from({ length: 80 }, (_, i) => ({ key: `part:${i}`, kind: "board", name: `A long board name ${i}` })),
  ];
  const edges = nodes.slice(1).map(n => ({ from: "part:s", to: n.key, kind: "lineage" }));
  const geometry = layoutAtlas(nodes, edges);
  for (const width of [350, 768, 1440, 1971]) {
    const bounds = { width, height: 650 };
    const points = new Map([...geometry].map(([key, value]) => [key, projectPoint(value, fitCamera(), bounds)]));
    const labels = atlasLabels(nodes, edges, points, "part:s", bounds, 12);
    assert.ok(labels.some(label => label.key === "part:s"));
    assert.ok(labels.length <= 8, `Dense neighbors must not all become labels at ${width}px`);
    for (const [i, label] of labels.entries()) {
      assert.ok(label.left >= 8 && label.right <= width - 8);
      assert.ok(label.top >= 8 && label.bottom <= bounds.height - 8);
      for (const other of labels.slice(i + 1)) {
        assert.ok(label.right + 6 <= other.left || other.right + 6 <= label.left || label.bottom + 4 <= other.top || other.bottom + 4 <= label.top);
      }
    }
  }
});
