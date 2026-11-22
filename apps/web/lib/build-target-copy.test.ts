// The build-target tier (Jr redesign plan, 2026-11-22). Owner-approved copy, verbatim:
// "Build target for <board>: the project's PlatformIO config at commit <sha7> selects this board's definition
// (env <env>). Configuration only: not built or tested on hardware." Order: below Unverified, above Broken.
import { test } from "node:test";
import assert from "node:assert/strict";
import { tierClaim } from "./flash-copy.ts";
import { RECIPE_TIER_LABEL, RECIPE_TIER_ORDER } from "./format.ts";

test("the build-target sentence is the owner-approved copy, with the claim's commit and env", () => {
  assert.equal(
    tierClaim("build-target", "Heltec WiFi Kit 32 V3", { sha: "971c066b37dbe3dbb9ac1096d9e72f32ab5b3452", env: "heltecv3demo" }),
    "Build target for Heltec WiFi Kit 32 V3: the project's PlatformIO config at commit 971c066 selects this board's definition (env heltecv3demo). Configuration only: not built or tested on hardware.",
  );
});

test("without its claim the sentence never invents a commit or env, and never says 'runs on'", () => {
  const line = tierClaim("build-target", "Heltec WiFi Kit 32 V3");
  assert.equal(line, "Build target for Heltec WiFi Kit 32 V3: the project's PlatformIO config selects this board's definition. Configuration only: not built or tested on hardware.");
  assert.doesNotMatch(line, /runs on|works on|known.good/i);
});

test("the tier sits below Unverified and above Broken, labelled Build target", () => {
  const order = [...RECIPE_TIER_ORDER] as string[];
  assert.equal(order.indexOf("build-target"), order.indexOf("unverified") + 1);
  assert.equal(order.indexOf("broken"), order.indexOf("build-target") + 1);
  assert.equal(RECIPE_TIER_LABEL["build-target"], "Build target");
});
