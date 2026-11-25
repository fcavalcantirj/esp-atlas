# Incident ecf3f2c6da43: `quotes` red on tick PRs #2050 and #2052

- Fingerprint: `ecf3f2c6da43d8cbbc2a3ef6f93e60e96960a6420967f502ebc6d76a9dc5dbe2`
- Check: `pr-red:#2052:quotes` (also red on #2050)
- Verdict: **(b) the records are wrong, not main's code.** No code change. A human fixes the two records.

## MEASURED

- `quotes` (`python3 scripts/check_quotes.py`) fails on #2052 at `6b300842` (run 45361557000,
  job 138332621746) and on #2050 at `8ee0a478` (run 45361580775, job 138332696648). It reads each
  record the PR changes and requires every quoted span to appear on a page the record cites. Every
  cited page was fetched and readable. None were inconclusive.
- I reproduced it on 2026-11-24 around 10:04 UTC by running the same script at both PR heads
  (exit 1, same FAILs). I also ran it on `main` at `d4bd52bf` against the two records as they are on
  main: exit 1, `2 record(s) with quotes: 0 pass, 2 FAIL; 34 quote(s): 29 pass, 5 FAIL`. The
  failing quotes are already on `main`. Neither tick PR changed them. #2052 adds `download_mode` and
  `getting_started` to the S3 Sense record and re-wraps the YAML. #2050 adds `getting_started` to the
  C5 record and re-wraps it. Because of that change, each record falls under the "changed records"
  check.
- `data/boards/seeed/xiao-esp32s3-sense/board.md`, authored 2026-09-11 (#267), cites only
  `https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/` and the pinout PNG. Three quotes are no
  longer on that page:
  - `"1x OV3660 camera sensor"`: the Specifications table's Built-in Sensors row now reads
    "1x OV5640 camera sensor (fixed-focus)".
  - `"The OV2640 camera has been discontinued, and the subsequent XIAO ESP32-S3 Sense uses the OV3660
    camera model."`: the page now reads "... the subsequent XIAO ESP32-S3 Sense used the OV3660
    camera model. Due to the OV3660 being out of stock, the XIAO ESP32-S3 Sense camera is now
    upgraded to the OV5640 camera".
  - `"Detachable OV2640 camera sensor for 1600x1200 resolution and OV3660 camera sensor for 2048x1536
    compatible with OV5640 camera sensor"`: the page now reads "Detachable OV5640 camera sensor
    (fixed-focus) for 2592x1944 resolution (also compatible with the OV3660 camera sensor for
    2048x1536 and the OV2640 camera sensor for 1600x1200)".
- `data/boards/seeed/xiao-esp32c5/board.md`, authored 2026-09-11 (#267), has two quotes that are on
  none of its 4 cited pages:
  - `"Input voltage (Type-C)"`: the note itself says it comes from "sibling XIAO docs", and that page
    is not cited. It is on the S3 page above, not on the C5 page.
  - `"you can draw NmA"`: an `io.power_out OMITTED` note puts a placeholder in quotes to say the page
    lacks such a sentence. It is not a quotation of the page.
- The checker reads these pages correctly. On the same fetched C5 page it finds the record's other
  quotes, for example `"As small as a thumb(21x17.8mm)"` and `"PWM/Analog Pins"`.

## INFERRED

- Seeed rewrote the S3 Sense page after 2026-09-11. The camera is now an OV5640. The record's
  camera notes no longer match the source it cites, so it is stale data. The guard catches it
  correctly.
- The C5 record quotes text its citations do not hold. One quote comes from an uncited page, and the
  other is a placeholder written as a quote. The guard catches both correctly.
- Changing `check_quotes.py` to skip quotes a PR did not touch would turn both PRs green, but the
  stale S3 Sense camera claim would then pass. That loosens a fail-closed check, so it is not done
  here.
- Every later tick or demand PR that touches either record stays red on `quotes` until the records
  are fixed on `main`.

## What a human must do

1. S3 Sense: re-read the vendor page and re-quote the camera notes, `extras: camera` included, against
   its current wording (OV5640, fixed-focus). Then bump `verified` on the `*` source.
2. C5: either cite the page that holds "Input voltage (Type-C)" for `usb.connector` or drop that quote
   (the C5 page's own "USB Type-C" quotes already pass). Reword the `io.power_out OMITTED` note
   without quote marks around the placeholder.
3. Then merge `main` into #2050 and #2052 (the chores do this) and rerun `quotes`. An LLM does not
   author these record edits (`CLAUDE.md`, "North star").
