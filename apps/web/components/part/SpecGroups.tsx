import Link from "next/link";
import type { ReactNode } from "react";
import type { PartDetail } from "@/lib/api";
import { bandsLabel, dimensionsLabel, protocolsLabel, wifiLabel, yesNo } from "@/lib/format";
import { asBool, asNumber, asNumberArray, asString, asStringArray, fmObject } from "@/lib/frontmatter";

// Renders what the record states, grouped. Absent fields are omitted (never
// guessed) and empty groups disappear — the page mirrors the source-or-omit rule.

interface Row {
  label: string;
  value: ReactNode;
}

interface Group {
  key: string;
  title: string;
  note?: ReactNode;
  rows: Row[];
}

function row(label: string, value: ReactNode | null | undefined): Row | null {
  if (value === null || value === undefined || value === "") return null;
  return { label, value };
}

function compact(rows: (Row | null)[]): Row[] {
  return rows.filter((r): r is Row => r !== null);
}

function Chips({ values }: { values: string[] }) {
  if (values.length === 0) return null;
  return (
    <span className="spec-chips">
      {values.map((v) => (
        <span key={v} className="spec-chip">
          {v}
        </span>
      ))}
    </span>
  );
}

function chipsOrNull(values: string[]): ReactNode | null {
  return values.length ? <Chips values={values} /> : null;
}

export default function SpecGroups({ part }: { part: PartDetail }) {
  const fm = part.frontmatter;
  const soc = part.chain.soc;
  const inheritedNote =
    part.type !== "soc" && soc ? (
      <span className="spec-group-note">
        inherited from <Link href={`/parts/${encodeURIComponent(soc.id)}`}>{soc.name}</Link>
      </span>
    ) : undefined;

  const groups: Group[] = [];

  groups.push({
    key: "radios",
    title: "Radios",
    note: inheritedNote,
    rows: compact([
      row(
        "Wi-Fi",
        part.wifi_standard
          ? `${wifiLabel(part.wifi_standard)}${part.wifi_bands ? ` · ${bandsLabel(part.wifi_bands)}` : ""}`
          : "none",
      ),
      row("Bluetooth LE", part.ble_version ? `BLE ${part.ble_version}` : "none"),
      row("Bluetooth Classic", yesNo(part.bt_classic)),
      row(
        "802.15.4",
        part.ieee802154 === null ? null : part.ieee802154 ? (protocolsLabel(part.ieee802154_protocols) ?? "yes") : "no",
      ),
    ]),
  });

  const usb = fmObject(fm, "usb");
  const socUsb = part.type === "soc" ? usb : null;
  groups.push({
    key: "usb",
    title: "USB",
    rows: compact([
      row("Native USB", yesNo(part.usb_native)),
      row("Connector", asString(usb?.connector)),
      row("Bridge chip", usb?.bridge === "native" ? "none — SoC native USB" : asString(usb?.bridge)),
      row("USB type", asString(socUsb?.type)),
    ]),
  });

  if (part.type === "board") {
    const power = fmObject(fm, "power");
    groups.push({
      key: "board",
      title: "Board",
      rows: compact([
        row("Form factor", part.form_factor),
        row("Dimensions", dimensionsLabel(asNumberArray(fm.dimensions_mm))),
        row("Battery connector", yesNo(asBool(power?.battery_connector))),
        row("Charging", yesNo(asBool(power?.charging))),
      ]),
    });
    groups.push({
      key: "peripherals",
      title: "Display & extras",
      rows: compact([row("Display", asString(fm.display)), row("Extras", chipsOrNull(asStringArray(fm.extras)))]),
    });
  }

  if (part.type === "module") {
    const flash = asNumber(fm.flash_mb);
    const psram = asNumber(fm.psram_mb);
    groups.push({
      key: "module",
      title: "Module",
      rows: compact([
        row("Flash", flash !== null ? `${flash} MB` : null),
        row("PSRAM", psram !== null ? `${psram} MB` : null),
        row("Antenna", asString(fm.antenna)),
        row("Dimensions", dimensionsLabel(asNumberArray(fm.dimensions_mm))),
        row("Certifications", chipsOrNull(asStringArray(fm.certifications))),
      ]),
    });
  }

  if (part.type === "soc") {
    const cpu = fmObject(fm, "cpu");
    const lpCore = cpu ? fmObject(cpu, "lp_core") : null;
    const memory = fmObject(fm, "memory");
    const maxMhz = asNumber(cpu?.max_mhz);
    const lpMhz = asNumber(lpCore?.max_mhz);
    const psramOptions = asNumberArray(memory?.in_package_psram_mb);
    const kb = (value: unknown) => {
      const n = asNumber(value);
      return n !== null ? `${n} KB` : null;
    };
    groups.push({
      key: "cpu",
      title: "CPU",
      rows: compact([
        row("Architecture", asString(cpu?.arch)),
        row("Cores", asNumber(cpu?.cores)),
        row("Max clock", maxMhz !== null ? `${maxMhz} MHz` : null),
        row("Extensions", chipsOrNull(asStringArray(cpu?.extensions))),
        row(
          "Low-power core",
          lpCore ? `${asString(lpCore.arch) ?? ""}${lpMhz !== null ? ` @ ${lpMhz} MHz` : ""}`.trim() : null,
        ),
      ]),
    });
    groups.push({
      key: "memory",
      title: "Memory",
      rows: compact([
        row("SRAM", kb(memory?.sram_kb)),
        row("LP SRAM", kb(memory?.lp_sram_kb)),
        row("RTC SRAM", kb(memory?.rtc_sram_kb)),
        row("ROM", kb(memory?.rom_kb)),
        row("In-package PSRAM options", psramOptions.length ? psramOptions.map((n) => `${n} MB`).join(", ") : null),
        row("External PSRAM", yesNo(asBool(memory?.psram_external))),
      ]),
    });
    groups.push({
      key: "interfaces",
      title: "Interfaces",
      rows: compact([row("Peripherals", chipsOrNull(asStringArray(fm.interfaces)))]),
    });
    groups.push({
      key: "security",
      title: "Security",
      rows: compact([row("Features", chipsOrNull(asStringArray(fm.security)))]),
    });
  }

  const visible = groups.filter((g) => g.rows.length > 0);

  return (
    <section aria-label="Specifications">
      <h2>Specifications</h2>
      <div className="spec-groups">
        {visible.map((group) => (
          <div key={group.key} className="spec-group">
            <h3>
              {group.title}
              {group.note}
            </h3>
            <dl className="spec-dl">
              {group.rows.map((r) => (
                <div key={r.label} style={{ display: "contents" }}>
                  <dt>{r.label}</dt>
                  <dd>{r.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    </section>
  );
}
