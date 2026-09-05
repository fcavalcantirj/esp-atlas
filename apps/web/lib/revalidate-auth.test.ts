import { test } from "node:test";
import assert from "node:assert/strict";
import { authorizeRevalidate } from "./revalidate-auth.ts";

test("an unset or empty secret leaves the route inert", () => {
  assert.equal(authorizeRevalidate("Bearer anything", undefined), "unconfigured");
  assert.equal(authorizeRevalidate("Bearer anything", ""), "unconfigured");
});

test("a missing or malformed Authorization header is unauthorized", () => {
  assert.equal(authorizeRevalidate(null, "s3cret"), "unauthorized");
  assert.equal(authorizeRevalidate("", "s3cret"), "unauthorized");
  assert.equal(authorizeRevalidate("s3cret", "s3cret"), "unauthorized");
  assert.equal(authorizeRevalidate("Basic s3cret", "s3cret"), "unauthorized");
});

test("a wrong token is unauthorized, whatever its length", () => {
  assert.equal(authorizeRevalidate("Bearer nope", "s3cret"), "unauthorized");
  assert.equal(authorizeRevalidate("Bearer s3cret-but-longer", "s3cret"), "unauthorized");
  assert.equal(authorizeRevalidate("Bearer s3cre", "s3cret"), "unauthorized");
});

test("the right token is ok, scheme case-insensitive", () => {
  assert.equal(authorizeRevalidate("Bearer s3cret", "s3cret"), "ok");
  assert.equal(authorizeRevalidate("bearer s3cret", "s3cret"), "ok");
});
