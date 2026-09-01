"""Deterministic, cited FAQ generation for SoC part pages -- promotes
spike/faq-c6's proven approach (spike/faq-c6/REPORT.md's GO/NO-GO) from
hand-authored proof to a real generator: TEMPLATE-FROM-SPECS, zero LLM.

Every answer is built by filling a sentence template from resolved
frontmatter paths on the SoC's own record (radios, cpu, memory, drive,
reserved_pins) plus, for the comparison item, a sibling SoC's record. Each
template function returns an item with a `claims` list -- (file, dotted
path, expected value, exact phrase) -- and `generate_faq` runs every item
through faq_grounding.ground_items before returning anything, so a template
bug or a data field that goes missing fails generation loudly instead of
shipping an untraceable claim.

Scope: type == "soc" only (see SPEC discussion -- that's where the search
demand is). `index_build._row_for` feeds `faq_text()` into a soc row's FTS
`notes`; `esp_atlas_core.search.get_part` feeds `public_items()` into the
API's PartDetail.faq for the web app to render + build FAQPage JSON-LD from.
"""
import re

from esp_atlas_core.faq_grounding import ground_items

_SOC_PATH = "data/socs/{id}/chip.md"
_SERIES_RE = re.compile(r"^esp32-([a-z]+)\d+$")

_ARCH_LABEL = {"risc-v": "RISC-V", "xtensa-lx6": "Xtensa LX6", "xtensa-lx7": "Xtensa LX7"}
_WIFI_NICE = {"wifi-4": "Wi-Fi 4", "wifi-6": "Wi-Fi 6"}


def _path_for(soc_id):
    return _SOC_PATH.format(id=soc_id)


def _core_word(n):
    return {1: "single-core", 2: "dual-core"}.get(n, f"{n}-core")


def _arch_label(arch):
    return _ARCH_LABEL.get(arch, arch)


def _wifi_nice(standard):
    return _WIFI_NICE.get(standard, standard)


def _claim(file, path, phrase, expect=None, kind=None):
    claim = {"file": file, "path": path, "in_answer": [phrase]}
    if kind is not None:
        claim["kind"] = kind
    if kind != "absent":
        claim["expect"] = expect
    return claim


# --- series/sibling selection ------------------------------------------------

def _series_key(soc_id):
    match = _SERIES_RE.match(soc_id)
    return match.group(1) if match else None


def _wifi_standard(fm):
    return ((fm.get("radios") or {}).get("wifi") or {}).get("standard")


def _ble_le(fm):
    return ((fm.get("radios") or {}).get("bluetooth") or {}).get("le")


def _ieee_present(fm):
    return ((fm.get("radios") or {}).get("ieee802154") or {}).get("present", False)


def _has_lp_core(fm):
    return "lp_core" in (fm.get("cpu") or {})


def _contrast_score(fm_a, fm_b):
    """How many headline radio/CPU capabilities differ -- used to pick the
    most INFORMATIVE same-series sibling to compare against, not just the
    numerically nearest model (e.g. for the C6, the C5 is one model number
    away but nearly spec-identical; the C3 differs on every dimension below
    and is what actually helps a buyer choose)."""
    return sum(
        [
            _wifi_standard(fm_a) != _wifi_standard(fm_b),
            _ble_le(fm_a) != _ble_le(fm_b),
            _ieee_present(fm_a) != _ieee_present(fm_b),
            _has_lp_core(fm_a) != _has_lp_core(fm_b),
        ]
    )


def pick_sibling(soc_id, fm, soc_by_id):
    """The other same-series SoC (id sharing the `esp32-<letters>` prefix,
    e.g. c6/c3/c5 are all "c") with the highest capability contrast against
    this one, tie-broken by id for determinism. None if this SoC has no
    series-mate in the dataset (e.g. the bare "esp32", or "esp32-p4")."""
    series = _series_key(soc_id)
    if series is None:
        return None
    candidates = [(cid, cfm) for cid, cfm in soc_by_id.items() if cid != soc_id and _series_key(cid) == series]
    if not candidates:
        return None
    candidates.sort(key=lambda pair: (-_contrast_score(fm, pair[1]), pair[0]))
    return candidates[0]


# --- templates ----------------------------------------------------------------

def _specs_item(soc_id, fm):
    path = _path_for(soc_id)
    name = fm["name"]
    cpu = fm["cpu"]
    memory = fm["memory"]
    radios = fm.get("radios") or {}
    claims = []

    core_word = _core_word(cpu["cores"])
    arch_label = _arch_label(cpu["arch"])
    mhz = cpu["max_mhz"]
    claims.append(_claim(path, "cpu.cores", core_word, expect=cpu["cores"]))
    claims.append(_claim(path, "cpu.arch", arch_label, expect=cpu["arch"]))
    claims.append(_claim(path, "cpu.max_mhz", f"up to {mhz} MHz", expect=mhz))

    lp_clause = ""
    if "lp_core" in cpu:
        lp_mhz = cpu["lp_core"]["max_mhz"]
        lp_clause = f", plus a separate low-power RISC-V core up to {lp_mhz} MHz"
        claims.append(_claim(path, "cpu.lp_core.max_mhz", f"low-power RISC-V core up to {lp_mhz} MHz", expect=lp_mhz))

    sram = memory["sram_kb"]
    sram_clause = f"{sram} KB of SRAM"
    claims.append(_claim(path, "memory.sram_kb", sram_clause, expect=sram))

    lp_sram_clause = ""
    if "lp_sram_kb" in memory:
        lp_sram = memory["lp_sram_kb"]
        lp_sram_clause = f" ({lp_sram} KB in the LP domain)"
        claims.append(_claim(path, "memory.lp_sram_kb", f"{lp_sram} KB in the LP domain", expect=lp_sram))

    rom_clause = ""
    if "rom_kb" in memory:
        rom = memory["rom_kb"]
        rom_clause = f" and {rom} KB of ROM"
        claims.append(_claim(path, "memory.rom_kb", f"{rom} KB of ROM", expect=rom))

    wifi = radios.get("wifi")
    if wifi:
        wifi_desc = _wifi_nice(wifi["standard"])
        claims.append(_claim(path, "radios.wifi.standard", wifi_desc, expect=wifi["standard"]))
    else:
        wifi_desc = "no Wi-Fi radio"
        claims.append(_claim(path, "radios.wifi", wifi_desc, expect=None))

    bt = radios.get("bluetooth")
    if bt:
        ble_desc = f"Bluetooth LE {bt['le']}"
        claims.append(_claim(path, "radios.bluetooth.le", ble_desc, expect=bt["le"]))
    else:
        ble_desc = "no Bluetooth radio"
        claims.append(_claim(path, "radios.bluetooth", ble_desc, expect=None))

    ieee = radios.get("ieee802154") or {}
    ieee_present = ieee.get("present", False)
    ieee_desc = "an 802.15.4 radio" if ieee_present else "no 802.15.4 radio"
    claims.append(_claim(path, "radios.ieee802154.present", ieee_desc, expect=ieee_present))

    usb_clause = ""
    usb = fm.get("usb")
    if usb is not None and "native" in usb:
        native = usb["native"]
        usb_clause = " It exposes native USB (Serial/JTAG)." if native else " It has no native USB."
        phrase = "native USB (Serial/JTAG)" if native else "no native USB"
        claims.append(_claim(path, "usb.native", phrase, expect=native))

    answer = (
        f"{name} is a {core_word} {arch_label} SoC clocked up to {mhz} MHz{lp_clause}. "
        f"It has {sram_clause}{lp_sram_clause}{rom_clause}. "
        f"Radios: {wifi_desc}, {ble_desc}, and {ieee_desc}.{usb_clause}"
    )
    return {"id": "specs", "question": f"What are the {name} specs / datasheet?", "answer": answer, "claims": claims}


def _gpio_count_item(soc_id, fm):
    path = _path_for(soc_id)
    name = fm["name"]
    total = (fm.get("drive") or {}).get("gpio_pads_total")
    if total is None:
        return None

    claims = [_claim(path, "drive.gpio_pads_total", f"{total} GPIO pads", expect=total)]
    reserved = fm.get("reserved_pins") or {}
    extra_clauses = []

    strapping = reserved.get("strapping")
    if strapping:
        n = len(strapping)
        phrase = f"{n} are strapping pins"
        extra_clauses.append(phrase)
        claims.append(_claim(path, "reserved_pins.strapping", phrase, expect=n, kind="count"))

    tied = reserved.get("usb_flash_tied")
    if tied:
        n = len(tied)
        phrase = f"{n} are tied to USB/flash"
        extra_clauses.append(phrase)
        claims.append(_claim(path, "reserved_pins.usb_flash_tied", phrase, expect=n, kind="count"))

    if extra_clauses:
        answer = f"The {name} has {total} GPIO pads in total, of which " + " and ".join(extra_clauses) + "."
    else:
        answer = f"The {name} has {total} GPIO pads in total."

    return {"id": "gpio-count", "question": f"What is the {name} pinout / GPIO count?", "answer": answer, "claims": claims}


def _radios_item(soc_id, fm):
    path = _path_for(soc_id)
    name = fm["name"]
    radios = fm.get("radios") or {}
    claims = []
    lines = []

    wifi = radios.get("wifi")
    if wifi:
        phrase = f"{_wifi_nice(wifi['standard'])} radio"
        claims.append(_claim(path, "radios.wifi.standard", phrase, expect=wifi["standard"]))
    else:
        phrase = "no Wi-Fi radio"
        claims.append(_claim(path, "radios.wifi", phrase, expect=None))
    lines.append(f"Wi-Fi: {phrase}.")

    bt = radios.get("bluetooth")
    if bt:
        phrase = f"Bluetooth LE {bt['le']}"
        claims.append(_claim(path, "radios.bluetooth.le", phrase, expect=bt["le"]))
    else:
        phrase = "no Bluetooth radio"
        claims.append(_claim(path, "radios.bluetooth", phrase, expect=None))
    lines.append(f"Bluetooth: {phrase}.")

    ieee = radios.get("ieee802154") or {}
    present = ieee.get("present", False)
    protocols = ieee.get("protocols")
    if present and protocols:
        proto_text = ", ".join(protocols)
        phrase = f"802.15.4 radio ({proto_text})"
        claims.append(_claim(path, "radios.ieee802154.present", "802.15.4 radio", expect=True))
        claims.append(_claim(path, "radios.ieee802154.protocols", proto_text, expect=protocols, kind="list-contains"))
    elif present:
        phrase = "802.15.4 radio"
        claims.append(_claim(path, "radios.ieee802154.present", phrase, expect=True))
    else:
        phrase = "no 802.15.4 radio"
        claims.append(_claim(path, "radios.ieee802154.present", phrase, expect=False))
    lines.append(f"802.15.4: {phrase}.")

    answer = f"{name}'s wireless radios: " + " ".join(lines)
    return {"id": "radios", "question": f"What wireless radios does the {name} have?", "answer": answer, "claims": claims}


def _lp_core_item(soc_id, fm):
    path = _path_for(soc_id)
    name = fm["name"]
    cpu = fm["cpu"]
    main_mhz = cpu["max_mhz"]
    main_clause = f"up to {main_mhz} MHz"
    claims = [_claim(path, "cpu.max_mhz", main_clause, expect=main_mhz)]

    if "lp_core" in cpu:
        lp = cpu["lp_core"]
        lp_mhz = lp["max_mhz"]
        lp_arch_label = _arch_label(lp.get("arch", cpu["arch"]))
        lp_clause = f"a separate {lp_arch_label} low-power core clocked up to {lp_mhz} MHz"
        claims.append(_claim(path, "cpu.lp_core.max_mhz", f"up to {lp_mhz} MHz", expect=lp_mhz))
        answer = f"Yes -- the {name} has {lp_clause}, alongside its main core ({main_clause})."
    else:
        phrase = "no separate low-power (LP) core"
        claims.append(_claim(path, "cpu.lp_core", phrase, kind="absent"))
        answer = f"No -- the {name} has {phrase}; only its main CPU core ({main_clause})."

    return {"id": "lp-core", "question": f"Does the {name} have a low-power (LP) core?", "answer": answer, "claims": claims}


def _chip_summary(fm, path, claims):
    cpu = fm["cpu"]
    core_word = _core_word(cpu["cores"])
    arch_label = _arch_label(cpu["arch"])
    mhz = cpu["max_mhz"]
    sram = fm["memory"]["sram_kb"]
    claims.append(_claim(path, "cpu.cores", core_word, expect=cpu["cores"]))
    claims.append(_claim(path, "cpu.arch", arch_label, expect=cpu["arch"]))
    claims.append(_claim(path, "cpu.max_mhz", f"up to {mhz} MHz", expect=mhz))
    claims.append(_claim(path, "memory.sram_kb", f"{sram} KB SRAM", expect=sram))
    return f"{core_word} {arch_label} SoC at up to {mhz} MHz ({sram} KB SRAM)"


def _radio_desc(fm, path, claims):
    radios = fm.get("radios") or {}
    wifi = radios.get("wifi")
    if wifi:
        wifi_desc = _wifi_nice(wifi["standard"])
        claims.append(_claim(path, "radios.wifi.standard", wifi_desc, expect=wifi["standard"]))
    else:
        wifi_desc = "no Wi-Fi"
        claims.append(_claim(path, "radios.wifi", wifi_desc, expect=None))

    bt = radios.get("bluetooth")
    if bt:
        ble_desc = f"BLE {bt['le']}"
        claims.append(_claim(path, "radios.bluetooth.le", ble_desc, expect=bt["le"]))
    else:
        ble_desc = "no BLE"
        claims.append(_claim(path, "radios.bluetooth", ble_desc, expect=None))

    ieee = radios.get("ieee802154") or {}
    present = ieee.get("present", False)
    ieee_desc = "802.15.4 yes" if present else "802.15.4 no"
    claims.append(_claim(path, "radios.ieee802154.present", ieee_desc, expect=present))

    return wifi_desc, ble_desc, ieee_desc


def _lp_desc(fm, path, claims):
    has_lp = _has_lp_core(fm)
    desc = "LP core yes" if has_lp else "LP core no"
    claims.append(_claim(path, "cpu.lp_core", desc, kind="present" if has_lp else "absent"))
    return desc


def _vs_sibling_item(soc_id, fm, soc_by_id):
    sibling = pick_sibling(soc_id, fm, soc_by_id)
    if sibling is None:
        return None
    sib_id, sib_fm = sibling
    if "cpu" not in sib_fm or "memory" not in sib_fm:
        return None
    path = _path_for(soc_id)
    sib_path = _path_for(sib_id)
    name = fm["name"]
    sib_name = sib_fm["name"]
    claims = []

    summary = _chip_summary(fm, path, claims)
    sib_summary = _chip_summary(sib_fm, sib_path, claims)
    wifi_d, ble_d, ieee_d = _radio_desc(fm, path, claims)
    sib_wifi_d, sib_ble_d, sib_ieee_d = _radio_desc(sib_fm, sib_path, claims)
    lp_d = _lp_desc(fm, path, claims)
    sib_lp_d = _lp_desc(sib_fm, sib_path, claims)

    answer = (
        f"The {name} is a {summary}; the {sib_name} is a {sib_summary}. "
        f"Wi-Fi: {wifi_d} vs {sib_wifi_d}. Bluetooth: {ble_d} vs {sib_ble_d}. "
        f"802.15.4: {ieee_d} vs {sib_ieee_d}. Low-power core: {lp_d} vs {sib_lp_d}."
    )
    return {
        "id": "vs-sibling",
        "question": f"{name} vs {sib_name}: what's different?",
        "answer": answer,
        "claims": claims,
    }


_TEMPLATES = (_specs_item, _gpio_count_item, _radios_item, _lp_core_item)


def build_faq_items(soc_id, fm, soc_by_id):
    """Fill every applicable template for one SoC -- ungrounded/inapplicable
    templates return None and are omitted (cite-or-omit at the item level:
    a SoC with no GPIO spec gets no gpio-count question, not a guessed one).

    `cpu`/`memory` are schema-required for a real soc record; a record
    missing either (e.g. a minimal test fixture, not real seeded data) gets
    no FAQ at all rather than a template crashing on a missing key.
    """
    if "cpu" not in fm or "memory" not in fm:
        return []
    items = [item for item in (t(soc_id, fm) for t in _TEMPLATES) if item is not None]
    sibling_item = _vs_sibling_item(soc_id, fm, soc_by_id)
    if sibling_item is not None:
        items.append(sibling_item)
    return items


def generate_faq(soc_id, fm, soc_by_id):
    """Build + ground every FAQ item for one SoC record.

    Raises FAQGroundingError (see faq_grounding) if any produced answer can't
    be traced to a real, sourced frontmatter field -- no ungrounded answer
    can ship. `soc_by_id` is {soc_id: frontmatter_dict} for every SoC in the
    dataset (index_build.build_index already builds this), used to pick the
    vs-sibling comparison.
    """
    return ground_items(build_faq_items(soc_id, fm, soc_by_id))


def faq_text(items):
    """Concatenated Q+A text -- what index_build feeds into parts_fts.notes."""
    return "\n".join(f"{item['question']}\n{item['answer']}" for item in items)


def public_items(items):
    """Strip internal grounding claims -- the shape the API/web layer sees."""
    return [{"id": item["id"], "question": item["question"], "answer": item["answer"]} for item in items]
