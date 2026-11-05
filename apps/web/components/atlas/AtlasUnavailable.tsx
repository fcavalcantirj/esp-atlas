"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import styles from "./AtlasExplorer.module.css";

export default function AtlasUnavailable() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return <section className={styles.unavailable} aria-busy={pending}>
    <p className={styles.eyebrow}>Atlas / catalog unavailable</p>
    <h1>The atlas couldn’t load.</h1>
    <p>The catalog is unavailable or its collections could not be reconciled. A complete view couldn’t be loaded; this does not mean the catalog is empty.</p>
    <div className={styles.actions}>
      <button type="button" className="btn btn--primary" onClick={() => startTransition(() => router.refresh())} disabled={pending}>{pending ? "Retrying…" : "Retry this view"}</button>
      <Link href="/status" className="btn">Service status ↗</Link>
      <Link href="/wizard" className="btn">Search the catalog ↗</Link>
    </div>
  </section>;
}
