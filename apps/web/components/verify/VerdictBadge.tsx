import type { Verdict } from "@/lib/verify-board";

const LABEL: Record<Verdict, string> = { match: "match", mismatch: "mismatch", unknown: "unknown" };

// Color plus the word — same rule as TrustTierBadge, never color alone.
export default function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <span className={`verdict-badge verdict-badge--${verdict}`}>{LABEL[verdict]}</span>;
}
