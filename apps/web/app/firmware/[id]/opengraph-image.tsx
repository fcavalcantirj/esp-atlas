import { ImageResponse } from "next/og";
import { fetchFirmware } from "@/lib/api-server";
import { firmwareCategoryLabel } from "@/lib/format";
import { SITE_NAME, SITE_TAGLINE } from "@/lib/site";

// Per-firmware social preview (og:image / twitter:image), rendered from the
// same record the page shows: name, category and maintainer, plus the SoCs
// it's verified to run on. Mirrors app/parts/[id]/opengraph-image.tsx exactly
// (size, fonts, colours, cached fetch + wordmark fallback) so the two social
// cards read as one system.
// The API fetch is the page's own (cached an hour, 3 s bound, never throws);
// on not_found / error the card falls back to the site wordmark so the route
// never answers 500. Colours are the light-theme tokens from globals.css.

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = `${SITE_NAME} — datasheet-verified ESP32 specs`;

const BG = "#ffffff";
const FG = "#16181d";
const MUTED = "#5c6370";
const BORDER = "#e3e6ea";
const ACCENT = "#0b6e8c";
const SERIF = "Georgia, 'Iowan Old Style', 'Times New Roman', serif";
const MONO = "'SF Mono', Menlo, Consolas, monospace";

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "56px 64px",
        background: BG,
        color: FG,
        fontFamily: SERIF,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: `1px solid ${BORDER}`, paddingBottom: 20 }}>
        <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 500, letterSpacing: 1 }}>{SITE_NAME}</span>
        <span style={{ fontFamily: MONO, fontSize: 18, letterSpacing: 3, textTransform: "uppercase", color: MUTED }}>datasheet-verified ESP32 specs</span>
      </div>
      {children}
    </div>
  );
}

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await fetchFirmware(id);

  if (result.status !== "ok") {
    return new ImageResponse(
      (
        <Frame>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ fontSize: 64, lineHeight: 1.05, letterSpacing: -1 }}>{SITE_TAGLINE}</div>
            <div style={{ fontSize: 28, color: MUTED }}>Every ESP32 SoC, module and dev board, every spec cited.</div>
          </div>
          <div style={{ fontFamily: MONO, fontSize: 20, color: MUTED }}>esp-atlas.com</div>
        </Frame>
      ),
      size,
    );
  }

  const firmware = result.data;
  const chips = firmware.socs.slice(0, 3);
  const nameSize = firmware.name.length > 40 ? 44 : firmware.name.length > 26 ? 54 : 64;

  return new ImageResponse(
    (
      <Frame>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, fontFamily: MONO, fontSize: 20, letterSpacing: 3, textTransform: "uppercase", color: MUTED }}>
            <span>{firmwareCategoryLabel(firmware.category)}</span>
            {firmware.maintainer && (
              <>
                <span style={{ color: BORDER }}>·</span>
                <span>{firmware.maintainer}</span>
              </>
            )}
          </div>
          <div style={{ fontSize: nameSize, lineHeight: 1.08, letterSpacing: -1 }}>{firmware.name}</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 20 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            {chips.map((soc) => (
              <span
                key={soc}
                style={{
                  fontFamily: MONO,
                  fontSize: 22,
                  padding: "10px 16px",
                  border: `1px solid ${ACCENT}`,
                  color: ACCENT,
                  borderRadius: 3,
                }}
              >
                {soc}
              </span>
            ))}
          </div>
          <div style={{ fontFamily: MONO, fontSize: 20, color: MUTED }}>{`esp-atlas.com/firmware/${firmware.id}`}</div>
        </div>
      </Frame>
    ),
    size,
  );
}
