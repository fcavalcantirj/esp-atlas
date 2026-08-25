"use client";

import Link from "next/link";
import { track } from "@/lib/analytics";
import type { Example, ExampleGroup } from "@/lib/api";
import { countLabel, explainNeeds } from "@/lib/need-labels";
import { exampleHref, SHELF_SEE_ALL } from "@/lib/routes";

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

function ExampleCard({ example }: { example: Example }) {
  const href = exampleHref(example);
  const onClick = () => track("example_click", { example: example.id, kind: example.kind });

  if (example.kind === "firmware") {
    return (
      <Link href={href} className="example-card" onClick={onClick}>
        <span className="example-card-label">{example.label}</span>
        {example.description && <span className="example-card-desc">{example.description}</span>}
        <span className="example-card-reason">
          Runs on {example.count} {example.count === 1 ? "board" : "boards"}
        </span>
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

export default function ExamplesGrid({ examples }: { examples: Example[] }) {
  if (examples.length === 0) return null;

  return (
    <div className="examples">
      {GROUPS.map((group) => {
        const inGroup = examples.filter((e) => e.group === group.id);
        if (inGroup.length === 0) return null;
        const seeAll = SHELF_SEE_ALL[group.id];
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
              {inGroup.map((example) => (
                <ExampleCard key={example.id} example={example} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
