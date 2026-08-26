// The Verify rail's matcher (SPEC-verify.md "The matcher"). Pure — no Web
// Serial, no esptool-js, no DOM — so it is unit-testable without a browser.
// Compares what the silicon reported this session against the board record
// esp-atlas cites, never asserting beyond what was actually read.

export type Verdict = "match" | "mismatch" | "unknown";

export interface DetectedPsram {
  present: boolean;
  /** Known only when the chip's own feature string states an exact size (e.g. ESP32-S3's "Embedded PSRAM 8MB"). */
  sizeMb: number | null;
}

/** What esptool-js's ESPLoader read from the connected chip this session. */
export interface DetectedChip {
  /** Lowercased chip family, e.g. "esp32-s3" — matches esp-atlas SoC ids 1:1. */
  chipFamily: string | null;
  flashMb: number | null;
  /** null = the PSRAM feature read failed/never ran, distinct from "read and absent". */
  psram: DetectedPsram | null;
  mac: string | null;
}

/** The cited record fields this rail checks against (board.soc / flash_mb / psram_mb). */
export interface BoardRecord {
  soc: string | null;
  flashMb: number | null;
  psramMb: number | null;
}

export interface FieldResult {
  name: string;
  detected: string;
  cited: string;
  verdict: Verdict;
}

export interface VerifyResult {
  fields: FieldResult[];
  /** Informational only — esp-atlas cites no per-unit MAC, so nothing to verify it against. */
  mac: string | null;
  overall: Verdict;
}

function mbText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "not cited";
  return `${value} MB`;
}

function chipField(detected: string | null, cited: string | null): FieldResult {
  const d = detected ? detected.toLowerCase() : null;
  const c = cited ? cited.toLowerCase() : null;
  return {
    name: "Chip family",
    detected: d ?? "not read",
    cited: c ?? "not cited",
    verdict: d === null || c === null ? "unknown" : d === c ? "match" : "mismatch",
  };
}

function flashField(detectedMb: number | null, citedMb: number | null | undefined): FieldResult {
  return {
    name: "Flash size",
    detected: detectedMb === null ? "not read" : `${detectedMb} MB`,
    cited: mbText(citedMb),
    verdict: detectedMb === null || citedMb === null || citedMb === undefined ? "unknown" : detectedMb === citedMb ? "match" : "mismatch",
  };
}

function psramField(detected: DetectedPsram | null, citedMb: number | null | undefined): FieldResult {
  const citedText = citedMb === 0 ? "no PSRAM" : mbText(citedMb);
  if (detected === null) {
    return { name: "PSRAM", detected: "not read", cited: citedText, verdict: "unknown" };
  }
  const detectedText = !detected.present ? "no PSRAM" : detected.sizeMb !== null ? `${detected.sizeMb} MB` : "present (size unknown)";
  if (citedMb === null || citedMb === undefined) {
    return { name: "PSRAM", detected: detectedText, cited: citedText, verdict: "unknown" };
  }
  let verdict: Verdict;
  if (!detected.present) {
    verdict = citedMb === 0 ? "match" : "mismatch";
  } else if (citedMb === 0) {
    verdict = "mismatch";
  } else if (detected.sizeMb !== null) {
    verdict = detected.sizeMb === citedMb ? "match" : "mismatch";
  } else {
    // Present on both sides but the chip's own feature string gave no exact size —
    // presence-only agreement, never claim a size reading esp-atlas doesn't have.
    verdict = "match";
  }
  return { name: "PSRAM", detected: detectedText, cited: citedText, verdict };
}

export function matchBoard(detected: DetectedChip, board: BoardRecord): VerifyResult {
  const fields = [chipField(detected.chipFamily, board.soc), flashField(detected.flashMb, board.flashMb), psramField(detected.psram, board.psramMb)];
  const overall: Verdict = fields.some((f) => f.verdict === "mismatch")
    ? "mismatch"
    : fields.every((f) => f.verdict === "match")
      ? "match"
      : "unknown";
  return { fields, mac: detected.mac, overall };
}
