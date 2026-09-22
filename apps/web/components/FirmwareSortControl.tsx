import Link from "next/link";
import { SORT_OPTIONS, sortHref } from "@/lib/firmware-sort";

// SPEC-firmware-ordering.md §3: real GET links (no onChange, no client-side
// reorder -- Golden Rule 3, the API sorts, this only navigates), so the
// control works with JavaScript disabled and every order is a shareable URL.
export default function FirmwareSortControl({ sort }: { sort: string }) {
  return (
    <nav className="firmware-sort" aria-label="Sort firmware">
      <span className="firmware-sort-label">Sort</span>
      <ul className="firmware-sort-list">
        {SORT_OPTIONS.map((option) => {
          const active = option.value === sort;
          return (
            <li key={option.value}>
              {active ? (
                <span className="firmware-sort-option is-active" aria-current="true">
                  {option.label}
                </span>
              ) : (
                <Link href={sortHref(option.value)} className="firmware-sort-option">
                  {option.label}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
