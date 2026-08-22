# esp-atlas

**A community-maintained, datasheet-verified knowledge base for the entire ESP32 family — and the boards built on it.**

> This is a collaborative project. The data lives as plain markdown you can read, correct, and extend by pull request. Every hard spec cites an official source. If it isn't verified, it isn't stated.

Most ESP guides are one person's blog, frozen at publish date, with specs copy-pasted and no way to *query* them. esp-atlas is the opposite: an open dataset anyone can fix, with a query layer on top that answers **"which ESP for X?"** — and only answers what the data actually supports.

## How it's organized

The real world has three layers, so the data does too — specs are declared once and inherited, never duplicated:

```
data/
  socs/       # the silicon (ESP32, -S3, -C6, -H4, -P4, …)
  modules/    # a SoC sealed in a can w/ flash/PSRAM/antenna (WROOM, WROVER, MINI…)
  boards/     # a module on a board w/ USB/regulator/headers — grouped by brand
  brands/     # vendor profiles
  companions/ # non-ESP radios that pair with ESPs (nRF24, CC1101, LTE/GNSS…)
schema/       # JSON Schema — the contract every file must satisfy
scripts/      # validate.py (the correctness gate) · build_index.py (the query artifact)
```

A board declares its `module`; the module declares its `soc`. Ask about a board and you get the chip's radios automatically — from one verified source of truth.

## Status

**v1 in progress — 26 parts seeded, all datasheet-verified:**
- **11 SoCs** (`data/socs/`) — the full current Espressif lineup.
- **6 modules** (`data/modules/`) — WROOM-32E, WROVER-E, S3-WROOM-1, C3-MINI-1, C6-WROOM-1, H2-MINI-1.
- **9 boards** (`data/boards/`) — Espressif DevKits (ESP32 / S3 / C6), Seeed XIAO (C3 / C6 / S3), LilyGO T-Display-S3, M5Stack CoreS3, Adafruit Feather ESP32-S3.

Every field cites its official source; the `soc → module → board` chain is enforced by CI. The query site is next — see [SPEC.md](SPEC.md). New parts are added the same way, by PR (or the oracle-loop bot).

## Contributing

Fixes and additions are welcome — a wrong number is a bug, and a missing board is an opportunity. Read [CONTRIBUTING.md](CONTRIBUTING.md). The one hard rule: **cite an official source for every spec, or leave it out.**

## Licensing

- **Data** (`data/`, `schema/`): [CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) — free to use, share alike.
- **Code** (`scripts/`, site): [MIT](LICENSE).

## Architecture

The repo is the single source of truth; the site is a pure function of it. See [ARCHITECTURE.md](ARCHITECTURE.md) for the query design (GitHub-as-dataset, the compiled index, and the grounded, "say-I'm-not-sure" chat layer).
