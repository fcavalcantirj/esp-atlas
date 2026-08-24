import type { Metadata } from "next";
import AskView from "@/components/AskView";

// INTERFACE-SPEC: "/ask full chat". The answer is generated per question, so
// nothing here is prerendered; the API caches by question + index version.
export const metadata: Metadata = {
  title: "Ask",
  description:
    "Ask a question about ESP32 chips, modules and boards and get an answer grounded in the atlas's cited records — or an honest \"not in esp-atlas yet\".",
  alternates: { canonical: "/ask" },
};

export default function AskPage() {
  return (
    <main id="main" className="container" tabIndex={-1}>
      <div className="home-intro">
        <h1>Ask</h1>
        <p>
          Answers are written from the atlas&apos;s own records and cite them. If the dataset doesn&apos;t cover
          something, the answer says so instead of guessing.
        </p>
      </div>
      <AskView />
    </main>
  );
}
