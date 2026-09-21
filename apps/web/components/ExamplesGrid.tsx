"use client";

import Link from "next/link";
import PopularityGlance from "@/components/PopularityGlance";
import { track } from "@/lib/analytics";
import type { Example, ExampleGroup } from "@/lib/api";
import { countLabel, explainNeeds } from "@/lib/need-labels";
import { revealCountLabel } from "@/lib/reveal";
import { exampleHref, SHELF_SEE_ALL } from "@/lib/routes";
import { useReveal } from "@/lib/use-reveal";

// The three soft shelves of SPEC-home-explorer §2, in the order the home shows
// them. Which shelf an example belongs to is decided by the API (its `group`),
// not here — this only names them. Every card is a real link (a firmware hub,
// or the wizard pre-filled with that query) and every shelf has a "see all", so
// each suggestion leads somewhere concrete, the way the spec wizard does.
const GROUPS: { id: ExampleGroup; title: string; hint: string }[] = [
  {
    id: "run-firmware",
    title: "Run a firmware",
    hint: "Projects with a verified recipe — see every board each one runs on.",
  },
  {
    id: "build-project",
    title: "Build a project",
    hint: "What you want the board to do, matched against real capability fields.",
  },
  { id: "just-show-me", title: "Just show me", hint: "Browse by the specs people actually ask for." },
];

function ExampleCard({ example, hidden = false }: { example: Example; hidden?: boolean }) {
  const href = exampleHref(example);
  const onClick = () => track("example_click", { example: example.id, kind: example.kind });
  const className = hidden ? "example-card is-hidden" : "example-card";

  if (example.kind === "firmware") {
    return (
      <Link href={href} className={className} onClick={onClick}>
        <span className="example-card-label">{example.label}</span>
        {example.description && <span className="example-card-desc">{example.description}</span>}
        <span className="example-card-reason">
          Runs on {example.count} {example.count === 1 ? "board" : "boards"}
        </span>
        <PopularityGlance popularity={{ stars: example.stars, forks: example.forks }} />
      </Link>
    );
  }

  // The subtitle names the real fields the query filters on — the teaching
  // layer of §4. Never a generated claim about why a board is good.
  const reason = explainNeeds(example.needs);

  return (
    <Link href={href} className="example-card" onClick={onClick}>
      <span className="example-card-label">{example.label}</span>
      <span className="example-card-reason">
        {countLabel(example.count, example.needs)}
        {reason && ` · ${reason}`}
      </span>
    </Link>
  );
}

// The API's run-firmware examples already cover the whole catalog, popularity
// ranked (esp_atlas_core.examples._firmware_examples — every firmware has
// >=1 recipe). SPEC-firmware-popularity.md §1/D4 makes this shelf the same
// full ranked/paginated browse as /firmware, not a curated teaser; the other
// two shelves are small fixed candidate lists and stay fully rendered.
const RUN_FIRMWARE: ExampleGroup = "run-firmware";

export default function ExamplesGrid({ examples }: { examples: Example[] }) {
  const firmwareCount = examples.filter((e) => e.group === RUN_FIRMWARE).length;
  const { revealed, hasMore, showMore } = useReveal(firmwareCount);

  if (examples.length === 0) return null;

  return (
    <div className="examples">
      {GROUPS.map((group) => {
        const inGroup = examples.filter((e) => e.group === group.id);
        if (inGroup.length === 0) return null;
        const seeAll = SHELF_SEE_ALL[group.id];
        const isFirmwareShelf = group.id === RUN_FIRMWARE;
        return (
          <section className="example-group" key={group.id} aria-labelledby={`examples-${group.id}`}>
            <div className="example-group-head">
              <h2 className="example-group-title" id={`examples-${group.id}`}>
                {group.title}
              </h2>
              <Link
                href={seeAll.href}
                className="example-group-seeall"
                onClick={() => track("shelf_see_all", { shelf: group.id, href: seeAll.href })}
              >
                {seeAll.label} ›
              </Link>
            </div>
            <p className="example-group-hint">{group.hint}</p>
            <div className="example-grid">
              {inGroup.map((example, i) => (
                <ExampleCard key={example.id} example={example} hidden={isFirmwareShelf && i >= revealed} />
              ))}
            </div>
            {isFirmwareShelf && (
              <div className="reveal-footer">
                <p className="reveal-count">{revealCountLabel(revealed, inGroup.length)}</p>
                {hasMore && (
                  <button type="button" className="btn" onClick={showMore}>
                    Show more
                  </button>
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
