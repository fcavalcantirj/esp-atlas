"use client";

import { useEffect } from "react";
import Link from "next/link";
import { track } from "@/lib/analytics";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    track("api_error", { endpoint: "page", status: error.digest ?? error.name });
  }, [error]);

  return (
    <main id="main" className="container container--narrow" tabIndex={-1}>
      <h1>Something went wrong</h1>
      <p className="lead">The page failed to render. The dataset itself is fine — this is the site, not the data.</p>
      <p className="error mono">{error.message}</p>
      <p>
        <button type="button" className="btn btn--primary" onClick={() => reset()}>
          Try again
        </button>{" "}
        <Link href="/" className="btn">
          Back to the wizard
        </Link>
      </p>
    </main>
  );
}
