import BoardFirmware from "@/components/part/BoardFirmware";
import ChipChain from "@/components/part/ChipChain";
import PartBody from "@/components/part/PartBody";
import PartHeader from "@/components/part/PartHeader";
import RelatedParts from "@/components/part/RelatedParts";
import SocHub from "@/components/part/SocHub";
import SourcesList from "@/components/part/SourcesList";
import SpecGroups from "@/components/part/SpecGroups";
import type { RecipeRow } from "@/components/RecipeGroupList";
import TrackedLink from "@/components/TrackedLink";
import VerifyBoard from "@/components/verify/VerifyBoard";
import type { PartDetail } from "@/lib/api";
import { asStringArray } from "@/lib/frontmatter";
import { editSourceUrl, newIssueUrl, viewSourceUrl } from "@/lib/github";

// Presentational: used by the server-rendered page and by the client fallback.
// boardFirmwareRows is only fetched server-side (board pages, see
// app/parts/[id]/page.tsx) — the client fallback renders without it, same
// graceful degradation as everything else on a cold API.
export default function PartDetailView({
  part,
  boardFirmwareRows = null,
}: {
  part: PartDetail;
  boardFirmwareRows?: RecipeRow[] | null;
}) {
  const notes = asStringArray(part.frontmatter.notes);
  // A SoC page is the hub for everything built on the chip: the list is promoted
  // to the main column (SocHub) and the aside only points at it.
  const isHub = part.type === "soc" && part.related.length > 0;
  const issueUrl = newIssueUrl({
    title: `Data issue: ${part.name} (${part.id})`,
    body: `Part: ${part.name} (\`${part.id}\`)\nFile: \`${part._path}\`\n\n**What is wrong:**\n\n\n**Official source that shows the correct value:**\n\n`,
  });

  return (
    <div className="part-layout">
      <div className="part-main">
        <PartHeader part={part} />
        <ChipChain part={part} />
        <PartBody body={part.body} />
        <SpecGroups part={part} />
        {part.type === "board" && (
          <VerifyBoard boardName={part.name} board={{ soc: part.soc_ref, flashMb: part.flash_mb, psramMb: part.psram_mb }} />
        )}
        {part.type === "board" && boardFirmwareRows !== null && <BoardFirmware rows={boardFirmwareRows} />}
        {isHub && <SocHub part={part} />}
        {notes.length > 0 && (
          <section aria-label="Notes">
            <h2>Notes</h2>
            <ul className="part-notes">
              {notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
      <aside className="part-aside" aria-label="Sources and related parts">
        <div className="aside-card">
          <h2>Sources</h2>
          <SourcesList part={part} />
        </div>
        <div className="aside-card">
          <h2>Contribute</h2>
          <ul className="aside-links">
            <li>
              <TrackedLink href={editSourceUrl(part._path)} linkType="github_edit" extra={{ part_id: part.id }}>
                Edit this record on GitHub
              </TrackedLink>
            </li>
            <li>
              <TrackedLink href={viewSourceUrl(part._path)} linkType="github_view" extra={{ part_id: part.id }}>
                View the markdown source
              </TrackedLink>
            </li>
            <li>
              <TrackedLink href={issueUrl} linkType="new_issue" extra={{ part_id: part.id }}>
                Report a wrong or missing spec
              </TrackedLink>
            </li>
          </ul>
        </div>
        <div className="aside-card">
          <h2>Related parts</h2>
          {isHub ? (
            <p className="aside-pointer">
              <a href="#on-chip">
                All {part.related.length} boards and modules on this chip
              </a>
            </p>
          ) : (
            <RelatedParts part={part} />
          )}
        </div>
      </aside>
    </div>
  );
}
