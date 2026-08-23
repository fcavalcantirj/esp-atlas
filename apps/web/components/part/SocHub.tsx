import PartResultCard from "@/components/PartResultCard";
import type { PartDetail } from "@/lib/api";

// The SoC page's hub section: every module and board built on the chip, as a
// plain server-rendered list (the same index rows as search results). The list
// is the core's `related` for the chip — already ordered by type, then name —
// so there is nothing to filter or rank here.
export default function SocHub({ part }: { part: PartDetail }) {
  if (part.related.length === 0) return null;
  return (
    <section className="soc-hub" aria-labelledby="on-chip">
      <h2 id="on-chip">
        Boards and modules on {part.name} ({part.related.length})
      </h2>
      <ul className="results-list">
        {part.related.map((record, index) => (
          <PartResultCard key={record.id} part={record} origin="browse" position={index + 1} />
        ))}
      </ul>
    </section>
  );
}
