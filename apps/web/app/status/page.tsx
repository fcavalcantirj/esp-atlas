import type { Metadata } from "next";
import Link from "next/link";
import StatusPanel from "@/components/StatusPanel";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";

const TITLE = "Status — live system health";
const DESCRIPTION = "Live health of the esp-atlas API, dataset and catalog, computed fresh on every request.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: "/status" },
  openGraph: { type: "website", siteName: SITE_NAME, title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, url: "/status", images: [OG_IMAGE] },
  twitter: { card: "summary_large_image", title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, images: [OG_IMAGE.url] },
};

export default function StatusPage() {
  return (
    <main id="main" className="container container--narrow" tabIndex={-1}>
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">Status</span>
      </nav>
      <h1>Status</h1>
      <p className="lead">{DESCRIPTION}</p>
      <StatusPanel />
    </main>
  );
}
