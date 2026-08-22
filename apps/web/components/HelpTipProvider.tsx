"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

// One open tip at a time, site-wide. Opening a tip closes the previous one;
// clicking anywhere outside the open tip, or pressing Escape, closes it.
interface HelpTipContextValue {
  openId: string | null;
  setOpenId: (id: string | null) => void;
}

const HelpTipContext = createContext<HelpTipContextValue>({ openId: null, setOpenId: () => {} });

export const HELP_TIP_ATTR = "data-help-tip-id";

export function HelpTipProvider({ children }: { children: React.ReactNode }) {
  const [openId, setOpenIdState] = useState<string | null>(null);
  const setOpenId = useCallback((id: string | null) => setOpenIdState(id), []);

  useEffect(() => {
    if (openId === null) return;

    function onPointerDown(event: PointerEvent) {
      const target = event.target as Element | null;
      const owner = target?.closest?.(`[${HELP_TIP_ATTR}]`) as HTMLElement | null;
      if (owner?.getAttribute(HELP_TIP_ATTR) === openId) return; // click inside the open tip
      setOpenIdState(null);
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenIdState(null);
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openId]);

  const value = useMemo(() => ({ openId, setOpenId }), [openId, setOpenId]);
  return <HelpTipContext.Provider value={value}>{children}</HelpTipContext.Provider>;
}

export function useHelpTip() {
  return useContext(HelpTipContext);
}
