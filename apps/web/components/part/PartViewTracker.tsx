"use client";

import { useEffect } from "react";
import type { PartRecord } from "@/lib/api";
import { track } from "@/lib/analytics";

export default function PartViewTracker({ part }: { part: PartRecord }) {
  useEffect(() => {
    track("part_view", { part_id: part.id, part_type: part.type, brand: part.vendor_or_brand, soc_ref: part.soc_ref });
  }, [part.id, part.type, part.vendor_or_brand, part.soc_ref]);
  return null;
}
