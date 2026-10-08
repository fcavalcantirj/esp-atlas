import BoardBrowse from "@/components/home/BoardBrowse";
import FirmwareWall from "@/components/home/FirmwareWall";
import PlugToFlashHero from "@/components/home/PlugToFlashHero";
import type { Firmware, PartRecord } from "@/lib/api";

// The plug-to-flash homepage (rebuild, 2026-10): one primary action --
// detect my board over Web Serial -- with a live intent search beside it,
// then the whole firmware catalog and the board long-tail below. Both the
// wall and the board browse render every card/link server-side (no "use
// client" needed here, the data is already resolved) so a crawler with no JS
// still sees the full catalog; app/page.tsx keeps the JsonLd graph and
// revalidate window that carries this page's AEO story.
export default function HomeView({ firmware, parts }: { firmware: Firmware[]; parts: PartRecord[] }) {
  const boards = parts.filter((part) => part.type === "board").sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div className="plug-home">
      <PlugToFlashHero firmware={firmware} parts={parts} />
      <FirmwareWall firmware={firmware} />
      <BoardBrowse boards={boards} />
    </div>
  );
}
