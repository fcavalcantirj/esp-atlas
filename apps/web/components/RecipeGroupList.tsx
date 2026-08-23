import Link from "next/link";
import TrustTierBadge from "@/components/TrustTierBadge";
import type { Recipe } from "@/lib/api";
import { flashMethodLabel, RECIPE_TIER_LABEL, RECIPE_TIER_ORDER } from "@/lib/format";

// The board <-> firmware edge, from either side: a board page groups its
// recipes by firmware, a firmware page groups its recipes by board. Both are
// the same "recipes, grouped by trust tier" shape — this renders that shape,
// informational only (no flash affordance yet, see SPEC-wizard.md P1/P2).
export interface RecipeRow {
  recipe: Recipe;
  href: string;
  name: string;
  meta?: string | null;
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
            {group.items.map(({ recipe, href, name, meta }) => {
              const flash = flashMethodLabel(recipe.flash?.method);
              return (
                <li key={recipe.id} className="recipe-row">
                  <Link href={href} className="recipe-row-name">
                    {name}
                  </Link>
                  <TrustTierBadge status={recipe.status} />
                  {meta && <span className="recipe-row-meta">{meta}</span>}
                  {flash && (
                    <span className="recipe-row-flash" title="How this firmware is flashed — informational only">
                      {flash}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </>
  );
}
