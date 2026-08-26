---
id: soldered-inkplate-2
type: board
brand: soldered
name: Inkplate 2
soc: esp32
flash_mb: 4
psram_mb: 8
form_factor: inkplate
price_tier: cheap
dimensions_mm:
- 65.3
- 35
- 9.8
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 2.13in 212x104 3-color E-Ink (red/black/white)
extras:
- e-ink
io:
  gpio_free: 5
notes:
- 4 MB flash
- MCP73831 Li-ion charger IC
- '8 uA low-power mode current'
- Official BOM lists the exact module ordering code ESP32-WROVER-IE-N4R8 (4 MB flash, 8 MB PSRAM)
- 'io.gpio_free=5 DERIVED, not quoted (SPEC-io-power.md §5.3). Vendor free-GPIO
  page table marks 13 native ESP32-WROVER-IE-N4R8 pins FREE (not tied to internal
  components): IO2,4,5,12,13,14,15,25,26,34,35,36,39 (note: the page''s own TL;DR
  prose list omits IO4, but the per-pin table marks it FREE -- used the table).
  Subtracting esp32''s reserved_pins that are among those free pads -- strapping
  {2,5,12,15} (4) and input_only {34,35,36,39} (4) -- gives 13 - 4 - 4 = 5 (remaining:
  IO4,13,14,25,26). Math not vendor-stated; verify before treating as exact.'
sources:
- field: '*'
  url: https://soldered.com/products/inkplate-2
  verified: '2026-08-22'
- field: power
  url: https://docs.soldered.com/inkplate/2/hardware/design/
  verified: '2026-08-22'
- field: psram_mb
  url: https://raw.githubusercontent.com/SolderedElectronics/Soldered-Inkplate-2-hardware-design/main/OUTPUTS/V1.2.3/Soldered%20Inkplate%202%20BOM.csv
  verified: '2026-08-24'
- field: io.gpio_free
  url: https://docs.soldered.com/inkplate/2/hardware/free-gpio/
  verified: '2026-08-26'
---

# Inkplate 2

A pocket-sized ESP32 board with a 2.13in three-color e-paper display, USB-C, and onboard Li-ion charging — built for ultra-low-power always-on labels and tags.
