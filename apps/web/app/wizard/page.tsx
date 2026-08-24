import type { Metadata } from "next";
import ExplorerView from "@/components/ExplorerView";
import { fetchExamples } from "@/lib/api-server";

// The spec wizard in full. The home leads with intent (SPEC-home-explorer §2);
// this page keeps the filter-first layout for people who know the specs they
// need, reachable from the top nav and from the home's "Spec wizard" drawer.
export const revalidate = 300;

export const metadata: Metadata = {
  title: "Wizard",
  description:
    "Filter every ESP32 SoC, module and dev board by the capabilities you need — radio, memory, USB, form factor, budget — and see the reason each part matched.",
  alternates: { canonical: "/wizard" },
};

export default async function WizardPage() {
  const examples = await fetchExamples();

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
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
