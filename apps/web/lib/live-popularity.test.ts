import { test } from "node:test";
import assert from "node:assert/strict";
import { popularityIdentity, popularityResponse, readLivePopularity } from "./live-popularity.ts";

const source = "https://github.com/example/project";
const record = {
  id: "example", url: source,
  popularity: { stars: 10, forks: 2, github_repo_id: 123, github_as_of: "2026-11-06T21:00:00Z" },
  sources: ["popularity.github_repo_id", "popularity.github_as_of"].map(field => ({ field, url: source, verified: "2026-11-06" })),
};
const now = Date.parse("2026-11-07T01:00:30Z");
const response = (outcome = "fresh") => ({
  firmware_id: "example", outcome,
  catalog: { stars: 10, forks: 2, github_as_of: record.popularity.github_as_of, source_url: source, repo_id: 123 },
  github: { stars: 0, forks: 0, observed_at: "2026-11-07T01:00:00Z", source_url: source, repo_id: 123 },
  retry_after_seconds: null,
});
const identity = popularityIdentity(record)!;

test("only a canonical cited identity can request an overlay", () => {
  assert.equal(identity.repoId, 123);
  for (const url of ["https://example.com/project", source + "/issues", source + "?q=x", source + "/", "http://github.com/example/project"]) {
    assert.equal(popularityIdentity({ ...record, url }), null);
  }
  assert.equal(popularityIdentity({ ...record, sources: record.sources.slice(1) }), null);
  for (const github_repo_id of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(popularityIdentity({ ...record, popularity: { ...record.popularity, github_repo_id } }), null);
  }
  assert.equal(popularityIdentity({ ...record, popularity: { ...record.popularity, github_as_of: "2026-02-30" } }), null);
});

test("fresh, cached and stale preserve real zero counts and their observation date", () => {
  for (const outcome of ["fresh", "cached", "stale"]) {
    const read = readLivePopularity(response(outcome), identity, now);
    assert.equal(read?.outcome, outcome);
    assert.equal(read?.github?.stars, 0);
    assert.equal(read?.github?.forks, 0);
    assert.equal(read?.github?.observed_at, "2026-11-07T01:00:00Z");
  }
});

test("unavailable and ineligible never turn a failure into an overlay", () => {
  for (const outcome of ["unavailable", "ineligible"]) {
    assert.deepEqual(readLivePopularity({ ...response(outcome), github: null }, identity, now), { outcome, github: null });
    assert.equal(readLivePopularity(response(outcome), identity, now), null);
  }
  assert.equal(readLivePopularity({ ...response(), github: null }, identity, now), null);
});

test("wrong firmware, source and repository identities are rejected", () => {
  const valid = response();
  for (const bad of [
    { ...valid, firmware_id: "other" },
    { ...valid, github: { ...valid.github, repo_id: 124 } },
    { ...valid, github: { ...valid.github, source_url: "https://github.com/other/project" } },
    { ...valid, catalog: { ...valid.catalog, repo_id: 124 } },
    { ...valid, catalog: { ...valid.catalog, source_url: "https://github.com/other/project" } },
  ]) assert.equal(readLivePopularity(bad, identity, now), null);
});

test("incomplete or imprecise numbers cannot replace cited counts", () => {
  for (const stars of [null, undefined, "20", true, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    const valid = response();
    assert.equal(readLivePopularity({ ...valid, github: { ...valid.github, stars } }, identity, now), null);
    assert.equal(readLivePopularity({ ...valid, github: { ...valid.github, forks: stars } }, identity, now), null);
  }
});

test("older, equal, impossible, ambiguous and far-future observations are rejected", () => {
  for (const observed_at of ["2026-11-06T20:59:59Z", record.popularity.github_as_of,
    "2026-02-30T01:00:00Z", "2026-11-07", "2026-11-07T01:00:00", "2099-01-01T00:00:00Z",
    "2026-11-07T25:00:00Z", "not a date"]) {
    const valid = response();
    assert.equal(readLivePopularity({ ...valid, github: { ...valid.github, observed_at } }, identity, now), null);
  }
  const valid = response();
  assert.equal(readLivePopularity({ ...valid, catalog: { ...valid.catalog, github_as_of: "2026-11-07T01:00:01Z" } }, identity, now), null);
});

test("date-only catalog snapshots require a later UTC day", () => {
  const dated = popularityIdentity({ ...record, popularity: { ...record.popularity, github_as_of: "2026-11-07" } })!;
  assert.equal(readLivePopularity(response(), dated, now), null);
  const earlier = popularityIdentity({ ...record, popularity: { ...record.popularity, github_as_of: "2026-11-06" } })!;
  assert.ok(readLivePopularity(response(), earlier, now)?.github);
});

test("malformed envelopes are rejected without throwing", () => {
  for (const payload of [null, [], {}, "ok", { ...response(), outcome: "live" },
    { ...response(), catalog: null }, { ...response(), retry_after_seconds: -1 }]) {
    assert.equal(readLivePopularity(payload, identity, now), null);
  }
});

test("optional responses are bounded, including streamed bodies without a length", async () => {
  assert.deepEqual(await popularityResponse(Response.json(response())), response());
  assert.equal(await popularityResponse(new Response("x", { status: 503 })), null);
  assert.equal(await popularityResponse(new Response("x", { headers: { "content-length": "16385" } })), null);
  assert.equal(await popularityResponse(new Response(" ".repeat(16385))), null);
  await assert.rejects(popularityResponse(new Response("{broken")), SyntaxError);
});
