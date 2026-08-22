import Link from "next/link";
import NotFoundTracker from "@/components/NotFoundTracker";
import TrackedLink from "@/components/TrackedLink";
import { contributingUrl } from "@/lib/github";

export default function NotFound() {
  return (
    <main id="main" className="container container--narrow" tabIndex={-1}>
      <NotFoundTracker />
      <h1>Not in esp-atlas yet</h1>
      <p className="lead">There is no page at this address — or the part you are looking for has not been added.</p>
      <p>
        <Link href="/" className="btn btn--primary">
          Back to the wizard
        </Link>{" "}
        <TrackedLink href={contributingUrl()} linkType="contributing" className="btn">
          Add a part
        </TrackedLink>
      </p>
    </main>
  );
}
