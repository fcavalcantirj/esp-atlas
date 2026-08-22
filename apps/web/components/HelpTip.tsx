"use client";

import { useId, useState } from "react";

export default function HelpTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();

  function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setOpen((o) => !o);
  }

  return (
    <span className="help-tip">
      <button
        type="button"
        className="help-tip-toggle"
        aria-expanded={open}
        aria-controls={id}
        aria-label={open ? "Hide help" : "Show help"}
        onClick={toggle}
      >
        ?
      </button>
      {open && (
        <span id={id} role="note" className="help-tip-text">
          {text}
        </span>
      )}
    </span>
  );
}
