import { RECIPE_TIER_LABEL } from "@/lib/format";

// A recipe's trust tier (SPEC-wizard.md "the honesty layer"). Color plus the
// word itself, never color alone — an unknown/omitted status still renders
// its raw value rather than nothing.
export default function TrustTierBadge({ status }: { status: string }) {
  const label = RECIPE_TIER_LABEL[status] ?? status;
  return <span className={`tier-badge tier-badge--${status}`}>{label}</span>;
}
