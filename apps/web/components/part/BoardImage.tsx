import type { PartDetail } from "@/lib/api";

type Images = { photo?: unknown; pinout?: unknown };

/**
 * The board's official imagery (backfilled into frontmatter.images, cite-or-omit):
 * a photo to IDENTIFY the board you're holding and the pinout diagram to WIRE it.
 * Renders nothing when the board has neither — graceful, like every other field.
 * Each opens the full-size official image in a new tab.
 */
export default function BoardImage({ part }: { part: PartDetail }) {
  const images = (part.frontmatter.images ?? {}) as Images;
  const items: { url: string; label: string }[] = [];
  if (typeof images.photo === "string" && images.photo) items.push({ url: images.photo, label: "Board" });
  if (typeof images.pinout === "string" && images.pinout) items.push({ url: images.pinout, label: "Pinout" });
  if (items.length === 0) return null;

  return (
    <section className="board-image" aria-label={`${part.name} imagery`}>
      <div className="board-image-grid">
        {items.map((it) => (
          <figure key={it.url} className="board-image-figure">
            <a href={it.url} target="_blank" rel="noopener noreferrer" title={`Open full-size ${it.label.toLowerCase()}`}>
              {/* eslint-disable-next-line @next/next/no-img-element -- external official vendor image, no next/image remote config */}
              <img src={it.url} alt={`${part.name} ${it.label.toLowerCase()}`} loading="lazy" />
            </a>
            <figcaption>{it.label}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
