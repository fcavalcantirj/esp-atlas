"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { track } from "@/lib/analytics";
import { FONT_SCALE_KEY } from "@/lib/site";

// ---- font scale store ------------------------------------------------------
// The value lives on <html style="--font-scale"> (applied pre-hydration by the
// inline script in app/layout.tsx) and in localStorage. useSyncExternalStore
// keeps the server snapshot at 1 so the buttons hydrate without a mismatch.

const FONT_SCALES = [0.875, 1, 1.125, 1.25, 1.5];

const listeners = new Set<() => void>();

function readScale(): number {
  try {
    const raw = document.documentElement.style.getPropertyValue("--font-scale") || localStorage.getItem(FONT_SCALE_KEY);
    const value = parseFloat(raw ?? "");
    return FONT_SCALES.includes(value) ? value : 1;
  } catch {
    return 1;
  }
}

function subscribe(callback: () => void) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

function applyScale(value: number) {
  document.documentElement.style.setProperty("--font-scale", String(value));
  try {
    localStorage.setItem(FONT_SCALE_KEY, String(value));
  } catch {
    // private mode / storage blocked — the in-page change still applies
  }
  listeners.forEach((listener) => listener());
}

function useFontScale() {
  return useSyncExternalStore(subscribe, readScale, () => 1);
}

const useMounted = () =>
  useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

// ---- controls ---------------------------------------------------------------

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();
  const isDark = mounted && resolvedTheme === "dark";

  function toggle() {
    const next = isDark ? "light" : "dark";
    setTheme(next);
    track("theme_change", { theme: next });
  }

  return (
    <button
      type="button"
      className="icon-btn"
      onClick={toggle}
      aria-pressed={isDark}
      aria-label={mounted ? (isDark ? "Switch to light theme" : "Switch to dark theme") : "Toggle theme"}
      title="Light / dark theme"
    >
      <span aria-hidden="true">{mounted ? (isDark ? "☀" : "☾") : "◐"}</span>
    </button>
  );
}

function FontSizeControls() {
  const scale = useFontScale();
  const index = FONT_SCALES.indexOf(scale);

  function step(direction: -1 | 1) {
    const next = FONT_SCALES[Math.min(FONT_SCALES.length - 1, Math.max(0, index + direction))];
    if (next === scale) return;
    applyScale(next);
    track("font_size_change", { scale: next, direction: direction > 0 ? "up" : "down" });
  }

  return (
    <div className="font-controls" role="group" aria-label="Text size">
      <button
        type="button"
        className="icon-btn"
        onClick={() => step(-1)}
        disabled={index <= 0}
        aria-label="Smaller text"
        title="Smaller text"
      >
        A<span className="font-controls-sign" aria-hidden="true">−</span>
      </button>
      <button
        type="button"
        className="icon-btn"
        onClick={() => step(1)}
        disabled={index >= FONT_SCALES.length - 1}
        aria-label="Larger text"
        title="Larger text"
      >
        A<span className="font-controls-sign" aria-hidden="true">+</span>
      </button>
    </div>
  );
}

export default function HeaderControls() {
  return (
    <div className="header-controls">
      <FontSizeControls />
      <ThemeToggle />
    </div>
  );
}
