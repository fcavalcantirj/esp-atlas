---
id: m5stick-c__nightdriverstrip
type: recipe
board: m5stick-c
firmware: nightdriverstrip
status: unverified
chip_family: esp32
flash:
  env: "m5demo"
notes: "nightdriverstrip builds the original M5StickC as env m5demo, which extends dev_m5stick_c (PlatformIO board m5stick-c, variant m5stack_stickc). Its other m5stick-c envs (installer_m5, m5plusdemo and the dev_m5stick_c_plus / dev_m5stick_c_plus2 sections) reuse the same PlatformIO id but require the StickC Plus or Plus2, so they are not evidence for this board. Derived from the repo's build file; no current passing build checked and not verified on hardware."
sources:
- field: '*'
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip
  verified: '2026-11-10'
- field: board
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/971c066b37dbe3dbb9ac1096d9e72f32ab5b3452/platformio.ini#L229-L231
  verified: '2026-11-10'
- field: flash.env
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/971c066b37dbe3dbb9ac1096d9e72f32ab5b3452/platformio.ini#L638-L639
  verified: '2026-11-10'
---

# m5stick-c x nightdriverstrip

`nightdriverstrip` builds the original M5StickC as env `m5demo` (`extends = dev_m5stick_c`; that section sets `board = m5stick-c` and `board_build.variant = m5stack_stickc`). Status `unverified` until someone with the hardware confirms it.

- `[dev_m5stick_c]` — https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/971c066b37dbe3dbb9ac1096d9e72f32ab5b3452/platformio.ini#L229-L231
- `[env:m5demo]` — https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/971c066b37dbe3dbb9ac1096d9e72f32ab5b3452/platformio.ini#L638-L639

Not evidence for this board: `installer_m5` extends `m5plusdemo`, which extends `dev_m5stick_c_plus2` ("Requires the M5StickC Plus2"), and the `dev_m5stick_c_plus` section requires the StickC Plus. Both reuse the generic PlatformIO id `m5stick-c`; they belong to `m5stick-cplus2` / `m5stick-cplus`.
