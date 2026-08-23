import { ImageResponse } from "next/og";
import { fetchPartDetail } from "@/lib/api-server";
import { specChips, typeLabel } from "@/lib/format";
import { SITE_NAME, SITE_TAGLINE } from "@/lib/site";

// Per-part social preview (og:image / twitter:image), rendered from the same
// record the page shows: name, kind, brand, the chip it is built on and up to
// three spec chips. No price tier — it is editorial, not a spec (SPEC.md).
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
  const result = await fetchPartDetail(id);

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

  const part = result.data;
  const chips = specChips(part).slice(0, 3);
  const builtOn = part.type === "soc" ? null : (part.chain.soc?.name ?? part.soc_ref);
  const nameSize = part.name.length > 40 ? 44 : part.name.length > 26 ? 54 : 64;

  return new ImageResponse(
    (
      <Frame>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, fontFamily: MONO, fontSize: 20, letterSpacing: 3, textTransform: "uppercase", color: MUTED }}>
            <span>{typeLabel(part.type)}</span>
            <span style={{ color: BORDER }}>·</span>
            <span>{part.vendor_or_brand}</span>
          </div>
          <div style={{ fontSize: nameSize, lineHeight: 1.08, letterSpacing: -1 }}>{part.name}</div>
          {builtOn && (
            <div style={{ display: "flex", gap: 10, fontSize: 28, color: MUTED }}>
              <span>Built on</span>
              <span style={{ color: FG }}>{builtOn}</span>
            </div>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 20 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            {chips.map((chip) => (
              <span
                key={chip.label}
                style={{
                  fontFamily: MONO,
                  fontSize: 22,
                  padding: "10px 16px",
                  border: `1px solid ${chip.on ? ACCENT : BORDER}`,
                  color: chip.on ? ACCENT : FG,
                  borderRadius: 3,
                }}
              >
                {chip.label}
              </span>
            ))}
          </div>
          <div style={{ fontFamily: MONO, fontSize: 20, color: MUTED }}>{`esp-atlas.com/parts/${part.id}`}</div>
        </div>
      </Frame>
    ),
    size,
  );
}
