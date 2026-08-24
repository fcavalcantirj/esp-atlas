"use client";

import Link from "next/link";
import { track } from "@/lib/analytics";
import type { Example, ExampleGroup, NeedsExample } from "@/lib/api";
import { countLabel, explainNeeds } from "@/lib/need-labels";

// The three soft shelves of SPEC-home-explorer §2, in the order the home shows
// them. Which shelf an example belongs to is decided by the API (its `group`),
// not here — this only names them.
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

function ExampleCard({ example, onExample }: { example: Example; onExample: (e: NeedsExample) => void }) {
  if (example.kind === "firmware") {
    return (
      <Link
        href={`/firmware/${encodeURIComponent(example.firmware)}`}
        className="example-card"
        onClick={() => track("example_click", { example: example.id, kind: "firmware" })}
      >
        <span className="example-card-label">{example.label}</span>
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
    <button type="button" className="example-card" onClick={() => onExample(example)}>
      <span className="example-card-label">{example.label}</span>
      <span className="example-card-reason">
        {countLabel(example.count, example.needs)}
        {reason && ` · ${reason}`}
      </span>
    </button>
  );
}

export default function ExamplesGrid({
  examples,
  onExample,
}: {
  examples: Example[];
  onExample: (example: NeedsExample) => void;
}) {
  if (examples.length === 0) return null;

  return (
    <div className="examples">
      {GROUPS.map((group) => {
        const inGroup = examples.filter((e) => e.group === group.id);
        if (inGroup.length === 0) return null;
        return (
          <section className="example-group" key={group.id} aria-labelledby={`examples-${group.id}`}>
            <h2 className="example-group-title" id={`examples-${group.id}`}>
              {group.title}
            </h2>
            <p className="example-group-hint">{group.hint}</p>
            <div className="example-grid">
              {inGroup.map((example) => (
                <ExampleCard key={example.id} example={example} onExample={onExample} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
