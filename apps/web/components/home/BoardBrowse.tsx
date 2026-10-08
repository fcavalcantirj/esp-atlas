"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { PartRecord } from "@/lib/api";
import { track } from "@/lib/analytics";
import { brandLabel } from "@/lib/brand";
import { revealCountLabel } from "@/lib/reveal";
import { useReveal } from "@/lib/use-reveal";

// SPEC-home rebuild §3: the board long-tail. Same "render everything, cap
// visibility client-side" idiom as FirmwareWall -- a crawler with no JS still
// gets a real <Link> for every board in the atlas.
export default function BoardBrowse({ boards }: { boards: PartRecord[] }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return boards;
    return boards.filter((board) => board.name.toLowerCase().includes(q));
  }, [boards, query]);
  const { revealed, hasMore, showMore } = useReveal(filtered.length);

  function onChange(value: string) {
    setQuery(value);
    if (value.trim().length > 1) track("home_board_search", { q: value });
  }

  return (
    <section className="board-browse" id="boards" aria-labelledby="boards-title">
      <div className="sechead">
        <h2 id="boards-title">Every board</h2>
        <span className="sechead-meta mono">{boards.length} catalogued</span>
      </div>
      <label className="intent-search-field board-search-field">
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4-4" />
        </svg>
        <span className="sr-only">Search boards</span>
        <input
          type="text"
          value={query}
          onChange={(e) => onChange(e.target.value)}
          placeholder={`search ${boards.length} boards — cardputer, xiao, wroom…`}
        />
      </label>
      {filtered.length === 0 ? (
        <p className="muted">No board matches &ldquo;{query}&rdquo;.</p>
      ) : (
        <ul className="board-grid">
          {filtered.map((board, index) => (
            <li key={board.id} className={index >= revealed ? "bcell is-hidden" : "bcell"}>
              <Link
                href={`/parts/${encodeURIComponent(board.id)}`}
                onClick={() =>
                  track("result_click", { part_id: board.id, part_type: "board", origin: "board_browse", position: index + 1 })
                }
              >
                <p className="bcell-name">{board.name}</p>
                <p className="bcell-meta mono">
                  {brandLabel(board)}
                  {board.soc_ref ? ` · ${board.soc_ref.toUpperCase()}` : ""}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <div className="reveal-footer">
        <p className="reveal-count mono">{revealCountLabel(revealed, filtered.length)}</p>
        {hasMore && (
          <button type="button" className="btn" onClick={showMore}>
            Load more boards
          </button>
        )}
      </div>
    </section>
  );
}
