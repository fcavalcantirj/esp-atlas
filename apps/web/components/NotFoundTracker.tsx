"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { track } from "@/lib/analytics";

export default function NotFoundTracker() {
  const pathname = usePathname();
  useEffect(() => {
    track("not_found", { path: pathname });
  }, [pathname]);
  return null;
}
