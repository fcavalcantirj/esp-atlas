import Link from "next/link";
import FlashAction from "@/components/flash/FlashAction";
import TrustTierBadge from "@/components/TrustTierBadge";
import type { Recipe } from "@/lib/api";
import type { FlashHandoff } from "@/lib/esp-web-tools";
import { flashMethodLabel, RECIPE_TIER_LABEL, RECIPE_TIER_ORDER } from "@/lib/format";

// The board <-> firmware edge, from either side: a board page groups its
// recipes by firmware, a firmware page groups its recipes by board. Both are
// the same "recipes, grouped by trust tier" shape — this renders that shape,
// each row carrying the Flash Wizard's action for that edge (SPEC-wizard P2b).
export interface RecipeRow {
  recipe: Recipe;
  href: string;
  name: string;
  meta?: string | null;
  /** Both ends of the edge by display name, for the flash panel's wording. */
  boardName: string;
  firmwareName: string;
  /** What the guided handoff may link to; omitted rows fall back to nothing but the reason text. */
  handoff?: FlashHandoff;
  /** The board's cited `usb.connector`, when known on this page. */
  usbConnector?: string | null;
}

export default function RecipeGroupList({ rows }: { rows: RecipeRow[] }) {
  const groups: { status: string; items: RecipeRow[] }[] = RECIPE_TIER_ORDER.map((status) => ({
    status,
    items: rows.filter((r) => r.recipe.status === status),
  })).filter((g) => g.items.length > 0);

  const known = new Set<string>(RECIPE_TIER_ORDER);
  const other = rows.filter((r) => !known.has(r.recipe.status));
  if (other.length > 0) groups.push({ status: "other", items: other });

  return (
    <>
      {groups.map((group) => (
        <div key={group.status} className="recipe-tier-group">
          <h3 className="recipe-tier-title">{RECIPE_TIER_LABEL[group.status] ?? group.status}</h3>
          <ul className="recipe-list">
            {group.items.map(({ recipe, href, name, meta, boardName, firmwareName, handoff, usbConnector }) => {
              const flash = flashMethodLabel(recipe.flash?.method);
              return (
                <li key={recipe.id} className="recipe-row">
                  <Link href={href} className="recipe-row-name">
                    {name}
                  </Link>
                  <TrustTierBadge status={recipe.status} />
                  {meta && <span className="recipe-row-meta">{meta}</span>}
                  {flash && (
                    <span className="recipe-row-flash" title="How this firmware is distributed">
                      {flash}
                    </span>
                  )}
                  <FlashAction
                    recipe={recipe}
                    targetName={name}
                    boardName={boardName}
                    firmwareName={firmwareName}
                    handoff={handoff ?? { repoUrl: null, flasherUrls: [] }}
                    usbConnector={usbConnector ?? null}
                  />
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </>
  );
}
