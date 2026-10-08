import type { Metadata } from "next";
import HomeView from "@/components/HomeView";
import JsonLd from "@/components/JsonLd";
import { fetchAllParts, fetchFirmwareList } from "@/lib/api-server";
import { homeGraph } from "@/lib/structured-data";
import "./home.css";

// Incremental static: the firmware list and part list below are rendered
// server-side (crawlable with no JS) and the page is regenerated every five
// minutes. At build time the API is not running, so the first static render
// omits them; the first request after deploy fills them in. Nothing here
// throws — a cold API degrades to an empty catalog, never an error page.
export const revalidate = 300;

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

export default async function Home() {
  const [parts, firmwareResult] = await Promise.all([fetchAllParts(), fetchFirmwareList()]);
  const firmware = firmwareResult.status === "ok" ? firmwareResult.data.results : [];

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      <JsonLd data={homeGraph()} />
      <HomeView firmware={firmware} parts={parts} />
    </main>
  );
}
