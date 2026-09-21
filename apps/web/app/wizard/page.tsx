import type { Metadata } from "next";
import ExplorerView from "@/components/ExplorerView";
import JsonLd from "@/components/JsonLd";
import { fetchExamples } from "@/lib/api-server";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";
import { wizardGraph } from "@/lib/structured-data";

// The spec wizard in full. The home leads with intent (SPEC-home-explorer §2);
// this page keeps the filter-first layout for people who know the specs they
// need, reachable from the top nav and from the home's "Spec wizard" drawer.
export const revalidate = 300;

const TITLE = "Spec wizard";
const DESCRIPTION =
  "Filter every ESP32 SoC, module and dev board by the capabilities you need — radio, memory, USB, form factor, budget — and see the reason each part matched.";

export const metadata: Metadata = {
  title: "Wizard",
  description: DESCRIPTION,
  alternates: { canonical: "/wizard" },
  openGraph: { type: "website", siteName: SITE_NAME, title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, url: "/wizard", images: [OG_IMAGE] },
  twitter: { card: "summary_large_image", title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, images: [OG_IMAGE.url] },
};

export default async function WizardPage() {
  const examples = await fetchExamples();

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      <JsonLd data={wizardGraph(DESCRIPTION)} />
      <div className="home-intro">
        <h1>Spec wizard</h1>
        <p>
          Pick the capabilities that matter and get every part in the atlas that fits, each with the reason it matched.
          Memory, radio, USB and form-factor specifics live under Advanced.
        </p>
      </div>
      <ExplorerView examples={examples.status === "ok" ? examples.data.results : []} />
    </main>
  );
}
