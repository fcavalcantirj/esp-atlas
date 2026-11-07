import test from "node:test";
import assert from "node:assert/strict";
import { catalogCachePolicy } from "./api-server.ts";
import { repositorySnapshot } from "./format.ts";

test("all metrics surfaces share short expiry and independent invalidation", () => {
  for (const path of ["/firmware", "/firmware?sort=forks", "/firmware/ruview", "/examples"]) {
    assert.deepEqual(catalogCachePolicy(path), { revalidate: 240, tags: ["catalog", "popularity"] });
  }
  for (const path of ["/parts", "/parts/esp32-s3", "/recipes", "/facets"]) {
    assert.deepEqual(catalogCachePolicy(path), { revalidate: 3600, tags: ["catalog"] });
  }
});

test("stale measurements retain their source date and fresh formatting is unchanged", () => {
  const observation = { stars: 0, github_as_of: "2026-11-07T19:00:00Z" };
  assert.equal(repositorySnapshot(observation), "GitHub repo · as of 2026-11-07 19:00 UTC");
  assert.equal(repositorySnapshot({ ...observation, stale: true }), "GitHub repo · as of 2026-11-07 19:00 UTC · stale");
  assert.equal(repositorySnapshot({ as_of: "2026-10-01", stale: true }), "GitHub repo · historical snapshot 2026-10-01 · stale");
});
