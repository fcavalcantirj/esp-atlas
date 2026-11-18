import { test } from "node:test";
import assert from "node:assert/strict";
import { CONSENT_REGIONS, bannerVisible, consentRequired, parseStoredConsent } from "./consent.ts";

test("the consent regions are the EEA, the UK and Switzerland, as ISO 3166-1 alpha-2", () => {
  const eu = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT",
    "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"];
  assert.deepEqual([...CONSENT_REGIONS].sort(), [...eu, "IS", "LI", "NO", "GB", "CH"].sort());
  assert.equal(CONSENT_REGIONS.length, 32);
});

test("consent is required in those regions and when the country is unknown; not elsewhere", () => {
  for (const c of ["DE", "de", "GB", "CH", "NO", "PL"]) assert.equal(consentRequired(c), true, c);
  for (const c of ["US", "BR", "CN", "IN", "RU"]) assert.equal(consentRequired(c), false, c);
  assert.equal(consentRequired(null), true);          // no geo header: ask rather than assume
  assert.equal(consentRequired(""), true);
});

test("a stored choice is read strictly", () => {
  assert.equal(parseStoredConsent("granted"), "granted");
  assert.equal(parseStoredConsent("denied"), "denied");
  for (const v of [null, "", "yes", "GRANTED", "1"]) assert.equal(parseStoredConsent(v), null);
});

test("the banner shows only to a visitor in a consent region who has not chosen yet", () => {
  assert.equal(bannerVisible(null, true), true);
  assert.equal(bannerVisible("granted", true), false);
  assert.equal(bannerVisible("denied", true), false);
  assert.equal(bannerVisible(null, false), false);
});
