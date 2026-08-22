import type { Metadata } from "next";
import HomeView from "@/components/HomeView";
import { SITE_TAGLINE } from "@/lib/site";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

export default function Home() {
  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      <div className="home-intro">
        <h1>{SITE_TAGLINE}</h1>
        <p>
          Every ESP32 SoC, module and dev board in one place, every spec cited to an official datasheet. Tell the wizard
          what you need and get the parts that fit — nothing guessed, nothing invented.
        </p>
      </div>
      <HomeView />
    </main>
  );
}
