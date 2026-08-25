"use client";

import Link from "next/link";
import TrackedLink from "@/components/TrackedLink";
import type { PartDetail } from "@/lib/api";
import { brandLabel } from "@/lib/brand";
import { PRICE_TIER_LABEL, PRICE_TIER_NOTE, typeLabel, typePlural } from "@/lib/format";
import { asStringArray } from "@/lib/frontmatter";
import { editSourceUrl } from "@/lib/github";
import { typeIndexPath } from "@/lib/routes";

export default function PartHeader({ part }: { part: PartDetail }) {
  const aka = asStringArray(part.frontmatter.aka);
  const indexPath = typeIndexPath(part.type);

  return (
    <header className="part-header">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        {indexPath ? <Link href={indexPath}>{typePlural(part.type)}</Link> : <span>{typePlural(part.type)}</span>}
        <span aria-hidden="true">›</span>
        <span aria-current="page">{part.name}</span>
      </nav>
      <div className="part-title-row">
        <h1>{part.name}</h1>
        <span className={`badge badge--${part.type}`}>{typeLabel(part.type)}</span>
      </div>
      <div className="part-meta">
        <span>
          by{" "}
          <Link href={`/brands/${part.vendor_or_brand}`}>
            <strong>{brandLabel(part)}</strong>
          </Link>
        </span>
        <span className="mono muted">{part.id}</span>
        {part.price_tier && (
          <span className="price-pill" title={PRICE_TIER_NOTE}>
            {PRICE_TIER_LABEL[part.price_tier] ?? part.price_tier}
          </span>
        )}
      </div>
      {aka.length > 0 && <p className="part-aka">Also known as: {aka.join(", ")}</p>}
      <div className="part-actions">
        <Link href={`/compare?ids=${encodeURIComponent(part.id)}`} className="btn btn--sm">
          Compare
        </Link>
        <TrackedLink
          href={editSourceUrl(part._path)}
          linkType="github_edit"
          extra={{ part_id: part.id }}
          className="btn btn--sm"
        >
          Edit on GitHub
        </TrackedLink>
      </div>
    </header>
  );
}
