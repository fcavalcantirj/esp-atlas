"use client";

import type { AnchorHTMLAttributes } from "react";
import { trackOutbound, type EventParams, type OutboundLinkType } from "@/lib/analytics";

interface TrackedLinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  href: string;
  linkType: OutboundLinkType;
  extra?: EventParams;
}

/** External <a> that fires an outbound_click event; opens in a new tab by default. */
export default function TrackedLink({ href, linkType, extra, children, onClick, ...rest }: TrackedLinkProps) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      {...rest}
      onClick={(e) => {
        trackOutbound(linkType, href, extra);
        onClick?.(e);
      }}
    >
      {children}
    </a>
  );
}
