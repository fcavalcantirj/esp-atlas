"use client";

import { useId, useRef, useState } from "react";
import { HELP_TIP_ATTR, useHelpTip } from "@/components/HelpTipProvider";
import { track } from "@/lib/analytics";

interface HelpTipProps {
  text: string;
  /** Short machine name of the field this tip explains, for analytics (e.g. "form", "budget"). */
  field: string;
}

const TIP_WIDTH = 280;

export default function HelpTip({ text, field }: HelpTipProps) {
  const id = useId();
  const { openId, setOpenId } = useHelpTip();
  const open = openId === id;
  const rootRef = useRef<HTMLSpanElement>(null);
  const [alignRight, setAlignRight] = useState(false);

  function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (open) {
      setOpenId(null);
      return;
    }
    // flip to the left when the popover would overflow the viewport (narrow sidebar / mobile)
    const rect = rootRef.current?.getBoundingClientRect();
    if (rect) setAlignRight(rect.left + TIP_WIDTH > window.innerWidth - 12);
    setOpenId(id);
    track("help_tip_open", { field });
  }

  return (
    <span className="help-tip" ref={rootRef} {...{ [HELP_TIP_ATTR]: id }}>
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
        <span id={id} role="note" className={`help-tip-text${alignRight ? " help-tip-text--right" : ""}`}>
          {text}
        </span>
      )}
    </span>
  );
}
