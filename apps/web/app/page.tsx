import Link from "next/link";
import WizardForm from "@/components/WizardForm";
import SearchBox from "@/components/SearchBox";

export default function Home() {
  return (
    <main className="container">
      <h1>esp-atlas</h1>
      <p>
        Which ESP32 for what you&apos;re building? See also <Link href="/compare">compare</Link>.
      </p>
      <WizardForm />
      <SearchBox />
    </main>
  );
}
