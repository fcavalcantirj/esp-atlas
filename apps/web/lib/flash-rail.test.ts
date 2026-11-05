import { test } from "node:test";
import { readFileSync } from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";
import type { Recipe } from "./api.ts";
import type { FlashHandoff, Manifest } from "./esp-web-tools.ts";
import { flashOpenPlan, flashPanelContent, inBrowserRail, installBlocked, type FlashPhase } from "./flash-rail.ts";

// The web half of the broken-install guard (planner room #271/#278): the API
// already refuses /manifest (404) and /flash-bin (403) for a broken recipe;
// the panel must offer no install path of its own on either artifact rail.

const BIN = "https://github.com/justcallmekoko/ESP32Marauder/releases/download/v1.15.1/esp32_marauder_v1_15_1_20260824_esp32c5devkitc1.bin";
const WIKI = "https://github.com/justcallmekoko/ESP32Marauder/wiki/ESP32%E2%80%90C5%E2%80%90DevKitC%E2%80%901";
const PROJECT_MANIFEST = "https://example.org/firmware/manifest.json";
const API_MANIFEST = "/api/manifest/esp32-c5-devkitc-1__esp32marauder.json";
const FLASHER = "https://example.org/web-flasher/";
const REPO = "https://github.com/justcallmekoko/ESP32Marauder";

// Mirrors data/recipes/esp32-c5-devkitc-1__esp32marauder/recipe.md.
const brokenReleaseBin: Recipe = {
  id: "esp32-c5-devkitc-1__esp32marauder",
  type: "recipe",
  board: "esp32-c5-devkitc-1",
  firmware: "esp32marauder",
  status: "broken",
  chip_family: "esp32-c5",
  firmware_version: "v1.15.1",
  flash: { method: "release-bin", bin_url: BIN, offset: "0x0", manifest_url: null, env: null, partition: null },
  verified_by: null,
  verified_at: null,
  notes: "Hardware test 2026-09-01: the v1.15.1 image boot-loops. Marked broken at v1.15.1 for this silicon revision.",
  sources: [
    { field: "flash.bin_url", url: BIN, verified: "2026-08-30" },
    { field: "*", url: WIKI, verified: "2026-08-30" },
  ],
};

const withRail = (recipe: Recipe, status: string, rail: "release-bin" | "project-manifest"): Recipe => ({
  ...recipe,
  status,
  flash:
    rail === "release-bin"
      ? { method: "release-bin", bin_url: BIN, offset: "0x0", manifest_url: null, env: null, partition: null }
      : { method: "esp-web-tools", bin_url: null, offset: null, manifest_url: PROJECT_MANIFEST, env: null, partition: null },
});

const RAILS = ["release-bin", "project-manifest"] as const;
const OTHER_TIERS = ["known-good", "reported", "declared", "unverified"] as const;

const manifest: Manifest = { name: "ESP32 Marauder", version: "v1.15.1", builds: [{ chipFamily: "ESP32-C5", parts: [] }] };
const handoff: FlashHandoff = { known: true, repoUrl: REPO, flasherUrls: [FLASHER] };

// Every phase a preflight can land in — including the ones a stale or late result could set.
const PHASES: FlashPhase[] = [
  { kind: "loading" },
  { kind: "ready", manifest, manifestUrl: API_MANIFEST },
  { kind: "ready", manifest, manifestUrl: PROJECT_MANIFEST },
  { kind: "handoff", reason: "This project ships its own web flasher; use it directly." },
  { kind: "broken" },
];

test("only the broken tier blocks install", () => {
  assert.equal(installBlocked({ status: "broken" }), true);
  for (const status of OTHER_TIERS) assert.equal(installBlocked({ status }), false, status);
});

test("opening a broken recipe never preflights a manifest, on either rail", () => {
  for (const rail of RAILS) {
    const recipe = withRail(brokenReleaseBin, "broken", rail);
    const url = rail === "release-bin" ? API_MANIFEST : PROJECT_MANIFEST;
    assert.deepEqual(flashOpenPlan(recipe, url), { kind: "broken" }, rail);
  }
  for (const method of ["web-flasher", "m5burner"]) {
    const recipe = { ...brokenReleaseBin, flash: { ...brokenReleaseBin.flash!, method } };
    assert.deepEqual(flashOpenPlan(recipe, null), { kind: "broken" }, method);
  }
});

test("positive control: every other tier still preflights its rail", () => {
  for (const status of OTHER_TIERS) {
    for (const rail of RAILS) {
      const url = rail === "release-bin" ? API_MANIFEST : PROJECT_MANIFEST;
      assert.deepEqual(flashOpenPlan(withRail(brokenReleaseBin, status, rail), url), { kind: "preflight", manifestUrl: url });
    }
    assert.deepEqual(flashOpenPlan({ ...brokenReleaseBin, status, flash: null }, null), { kind: "no_rail" });
  }
});

test("a broken recipe never renders an install button, a terminal command or an official-flasher handoff", () => {
  for (const rail of RAILS) {
    const recipe = withRail(brokenReleaseBin, "broken", rail);
    for (const phase of PHASES) {
      const content = flashPanelContent(recipe, phase, handoff, "ESP32-C5-DevKitC-1");
      assert.equal(content.kind, "broken", `${rail} / ${phase.kind}`);
      const text = JSON.stringify(content);
      for (const forbidden of ["esptool", API_MANIFEST, PROJECT_MANIFEST, FLASHER, BIN]) {
        assert.ok(!text.includes(forbidden), `${rail} / ${phase.kind} leaks ${forbidden}`);
      }
    }
  }
});

test("a stale ready result for a broken recipe is dropped, not rendered", () => {
  const late: FlashPhase = { kind: "ready", manifest, manifestUrl: API_MANIFEST };
  assert.equal(flashPanelContent(brokenReleaseBin, late, handoff, "ESP32-C5-DevKitC-1").kind, "broken");
});

test("the broken panel cites the recipe's own explanation and its docs, never the binary", () => {
  const content = flashPanelContent(brokenReleaseBin, { kind: "broken" }, handoff, "ESP32-C5-DevKitC-1");
  assert.equal(content.kind, "broken");
  if (content.kind !== "broken") return;
  assert.match(content.claim, /^Broken on ESP32-C5-DevKitC-1/);
  assert.equal(content.explanation, brokenReleaseBin.notes);
  assert.deepEqual(content.docs, [WIKI]);
});

test("a broken recipe without notes still explains itself", () => {
  const content = flashPanelContent({ ...brokenReleaseBin, notes: "  " }, { kind: "broken" }, handoff, "Board");
  assert.equal(content.kind, "broken");
  if (content.kind !== "broken") return;
  assert.ok(content.explanation.trim().length > 0);
});

test("a closed panel stays closed for every tier", () => {
  assert.deepEqual(flashPanelContent(brokenReleaseBin, { kind: "closed" }, handoff, "Board"), { kind: "closed" });
  assert.deepEqual(flashPanelContent({ ...brokenReleaseBin, status: "known-good" }, { kind: "closed" }, handoff, "Board"), {
    kind: "closed",
  });
});

test("positive control: other tiers keep the install rail, terminal fallback and handoff links", () => {
  for (const status of OTHER_TIERS) {
    const bin = withRail(brokenReleaseBin, status, "release-bin");
    const installed = flashPanelContent(bin, { kind: "ready", manifest, manifestUrl: API_MANIFEST }, handoff, "Board");
    assert.equal(installed.kind, "ready", status);
    if (installed.kind !== "ready") continue;
    assert.equal(installed.manifestUrl, API_MANIFEST);
    assert.deepEqual(installed.terminal, { chip: "esp32c5", offset: "0x0", file: BIN.split("/").pop(), url: BIN });

    const project = withRail(brokenReleaseBin, status, "project-manifest");
    const projectInstall = flashPanelContent(project, { kind: "ready", manifest, manifestUrl: PROJECT_MANIFEST }, handoff, "Board");
    assert.equal(projectInstall.kind, "ready", status);
    if (projectInstall.kind === "ready") assert.equal(projectInstall.terminal, null);

    const handed = flashPanelContent(bin, { kind: "handoff", reason: "use theirs" }, handoff, "Board");
    assert.deepEqual(handed, { kind: "handoff", reason: "use theirs", flasherUrls: [FLASHER], repoUrl: REPO }, status);

    assert.deepEqual(flashPanelContent(bin, { kind: "loading" }, handoff, "Board"), { kind: "loading" });
  }
});

test("the in-browser pill never glows for a broken recipe, on either rail", () => {
  for (const rail of RAILS) {
    assert.equal(inBrowserRail(withRail(brokenReleaseBin, "broken", rail), "closed"), false, rail);
    for (const status of OTHER_TIERS) {
      assert.equal(inBrowserRail(withRail(brokenReleaseBin, status, rail), "closed"), true, `${status} ${rail}`);
      assert.equal(inBrowserRail(withRail(brokenReleaseBin, status, rail), "handoff"), false, `${status} ${rail}`);
    }
  }
});

test("a preflight that resolved before the recipe turned broken cannot re-enable install, on either rail", () => {
  for (const rail of RAILS) {
    const url = rail === "release-bin" ? API_MANIFEST : PROJECT_MANIFEST;
    // The preflight ran while the recipe was still installable and landed "ready"…
    const installable = withRail(brokenReleaseBin, "reported", rail);
    const stale: FlashPhase = { kind: "ready", manifest, manifestUrl: url };
    assert.equal(flashPanelContent(installable, stale, handoff, "Board").kind, "ready", rail);
    // …then the record says broken: the same held phase renders no rail at all.
    const broken = withRail(brokenReleaseBin, "broken", rail);
    const content = flashPanelContent(broken, stale, handoff, "Board");
    assert.equal(content.kind, "broken", rail);
    assert.ok(!JSON.stringify(content).includes(url), `${rail} keeps the stale manifest`);
    assert.equal(inBrowserRail(broken, "ready"), false, rail);
  }
});

// FlashAction is a React client component node --test cannot render; pin at the
// source that it renders only the sanitized panel content, never its raw preflight.
const flashAction = readFileSync(path.resolve(import.meta.dirname, "../components/flash/FlashAction.tsx"), "utf8");

test("FlashAction renders only flashPanelContent, never its raw preflight state", () => {
  assert.match(flashAction, /const \[preflight, setPreflight\] = useState<FlashPhase>/);
  assert.match(flashAction, /const phase = flashPanelContent\(recipe, preflight, handoff, boardName\);/);
  // The raw state is read only to know whether the drawer is closed.
  const reads = flashAction.match(/\bpreflight\.\w+/g) ?? [];
  assert.ok(reads.length > 0 && reads.every((r) => r === "preflight.kind"), reads.join(", "));
  assert.equal((flashAction.match(/preflight\.kind(?! === "closed")/g) ?? []).length, 0);
});

test("FlashAction mounts the install button and the esptool command only on the ready content", () => {
  const ready = flashAction.indexOf('{phase.kind === "ready" && (');
  const handoffAt = flashAction.indexOf('{phase.kind === "handoff" && (');
  assert.ok(ready > 0 && handoffAt > ready);
  for (const marker of ["<esp-web-install-button", "esptool --chip", "Connect and flash"]) {
    const at = flashAction.indexOf(marker);
    assert.ok(at > ready && at < handoffAt, `${marker} must sit inside the ready block`);
    assert.equal(flashAction.indexOf(marker, at + 1), -1, `${marker} appears twice`);
  }
  assert.match(flashAction, /\{phase\.kind === "broken" && \(/);
});
