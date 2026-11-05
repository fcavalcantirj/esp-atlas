"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

type AtlasNavLinkProps = {
  href: string;
  className?: string;
  children: ReactNode;
};

/** Keep the server header's navigation current through client-side route changes. */
export default function AtlasNavLink({ href, className, children }: AtlasNavLinkProps) {
  const pathname = usePathname();
  const current = pathname === href || (href !== "/" && pathname?.startsWith(`${href}/`));

  return (
    <Link href={href} className={className} aria-current={current ? "page" : undefined}>
      {children}
    </Link>
  );
}
