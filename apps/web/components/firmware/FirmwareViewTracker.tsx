"use client";

import { useEffect } from "react";
import type { Firmware } from "@/lib/api";
import { track } from "@/lib/analytics";
import { firmwareViewParams } from "@/lib/firmware-tracking";

export default function FirmwareViewTracker({ firmware }: { firmware: Firmware }) {
  const primarySoc = firmware.socs[0] ?? null;
  useEffect(() => {
    track("part_view", firmwareViewParams(firmware.id, firmware.maintainer, primarySoc));
  }, [firmware.id, firmware.maintainer, primarySoc]);
  return null;
}
