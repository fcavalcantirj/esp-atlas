import { test } from "node:test";
import assert from "node:assert/strict";
import {
  familyFromChipId,
  familyFromMagic,
  hex32,
  identifyChip,
  parseSecurityInfoChipId,
  unknownChipMessage,
  type ChipDef,
} from "./chip-identify.ts";

// Mirrors esptool-js 0.6.1 (apps/web/package.json) — IMAGE_CHIP_ID and
// CHIP_DETECT_MAGIC_VALUE per target, magic-only chips carry chipId null.
const DEFS: ChipDef[] = [
  { family: "esp8266", chipId: null, magics: [0xfff0c101] },
  { family: "esp32", chipId: null, magics: [0x00f01d83] },
  { family: "esp32-s2", chipId: null, magics: [0x000007c6] },
  { family: "esp32-s3", chipId: 9, magics: [0x9] },
  { family: "esp32-c3", chipId: 5, magics: [0x6921506f, 0x1b31506f, 0x4881606f, 0x4361606f] },
  { family: "esp32-c5", chipId: 23, magics: [0x1101406f, 0x63e1406f, 0x5fd1406f] },
  { family: "esp32-c6", chipId: 13, magics: [0x2ce0806f] },
];

// The 2026-09-01 field case: ESP32-C5-DevKitC-1, chip rev v1.2, ROM eco3.
const C5_ECO3_MAGIC = 0x30e1706f;

function securityInfo(chipId: number, bytes = 20): Uint8Array {
  const p = new Uint8Array(bytes);
  p[12] = chipId & 0xff;
  p[13] = (chipId >>> 8) & 0xff;
  p[14] = (chipId >>> 16) & 0xff;
  p[15] = (chipId >>> 24) & 0xff;
  return p;
}

test("security-info payload: chip id is the little-endian u32 at bytes 12..15", () => {
  assert.equal(parseSecurityInfoChipId(securityInfo(23)), 23);
  assert.equal(parseSecurityInfoChipId(securityInfo(0x01020304)), 0x01020304);
  const p = securityInfo(23);
  p[15] = 0x80; // sign bit set — must stay unsigned
  assert.equal(parseSecurityInfoChipId(p), 0x80000017);
});

test("security-info payload: the 12-byte (ESP32-S2) form and a missing payload carry no chip id", () => {
  assert.equal(parseSecurityInfoChipId(securityInfo(2, 12)), null);
  assert.equal(parseSecurityInfoChipId(null), null);
  assert.equal(parseSecurityInfoChipId(new Uint8Array(0)), null);
});

test("C5 rev v1.2: magic 0x30e1706f is unknown to the table, chip-id 23 identifies it anyway", () => {
  assert.equal(familyFromMagic(C5_ECO3_MAGIC, DEFS), null, "the very gap that broke Verify");
  const id = identifyChip({ chipId: 23, magic: C5_ECO3_MAGIC }, DEFS);
  assert.ok(id);
  assert.equal(id.family, "esp32-c5");
  assert.equal(id.by, "chip-id");
  assert.equal(id.magicKnown, false, "the caller can warn that magic-only flashers will not detect this chip");
});

test("chip-id wins over a contradicting magic value", () => {
  const id = identifyChip({ chipId: 13, magic: 0x1101406f }, DEFS);
  assert.equal(id?.family, "esp32-c6");
  assert.equal(id?.by, "chip-id");
  assert.equal(id?.magicKnown, true);
});

test("classic ESP32: no chip-id (command unsupported) -> identified by magic", () => {
  const id = identifyChip({ chipId: null, magic: 0x00f01d83 }, DEFS);
  assert.equal(id?.family, "esp32");
  assert.equal(id?.by, "magic");
  assert.equal(id?.magicKnown, true);
});

test("chip-id 0 never maps to the classic ESP32 (it never answers the command)", () => {
  assert.equal(familyFromChipId(0, DEFS), null);
  assert.equal(identifyChip({ chipId: 0, magic: null }, DEFS), null);
});

test("nothing matched and no assumption -> null (the caller asks the human)", () => {
  assert.equal(identifyChip({ chipId: null, magic: C5_ECO3_MAGIC }, DEFS), null);
  assert.equal(identifyChip({ chipId: null, magic: null }, DEFS), null);
});

test("nothing matched but the board page cites a family the human accepted -> 'assumed', never 'magic'", () => {
  const id = identifyChip({ chipId: null, magic: C5_ECO3_MAGIC }, DEFS, "esp32-c5");
  assert.ok(id);
  assert.equal(id.family, "esp32-c5");
  assert.equal(id.by, "assumed");
  assert.equal(id.magicKnown, false);
  assert.equal(id.magic, C5_ECO3_MAGIC, "the unknown value travels with the result so it can be reported");
});

test("an assumption for a family esptool-js cannot drive is refused", () => {
  assert.equal(identifyChip({ chipId: null, magic: C5_ECO3_MAGIC }, DEFS, "esp32-h4"), null);
  assert.equal(identifyChip({ chipId: null, magic: C5_ECO3_MAGIC }, DEFS, ""), null);
});

test("a real identification is never downgraded to 'assumed' by an assumption", () => {
  const id = identifyChip({ chipId: 9, magic: 0x9 }, DEFS, "esp32-c5");
  assert.equal(id?.family, "esp32-s3");
  assert.equal(id?.by, "chip-id");
});

test("hex32 and the unknown-chip message carry the exact values a bug report needs", () => {
  assert.equal(hex32(C5_ECO3_MAGIC), "0x30e1706f");
  assert.equal(hex32(0x7c6), "0x000007c6");
  assert.equal(hex32(null), "not read");
  const msg = unknownChipMessage({ chipId: null, magic: C5_ECO3_MAGIC }, "0.6.1");
  assert.match(msg, /0x30e1706f/);
  assert.match(msg, /chip-id not reported/);
  assert.match(msg, /esptool-js 0\.6\.1/);
  assert.match(unknownChipMessage({ chipId: 23, magic: null }, "0.6.1"), /magic not read, chip-id 23/);
});
