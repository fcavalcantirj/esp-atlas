"use client";

// "Analytics choice" in the footer: withdrawing or changing consent is one click, like giving it.
import { CONSENT_RESET_EVENT } from "@/components/ConsentBanner";
import { resetConsent } from "@/lib/consent";

export default function ConsentResetButton() {
  return (
    <button
      type="button"
      className="link-button"
      onClick={() => {
        resetConsent();
        window.dispatchEvent(new Event(CONSENT_RESET_EVENT));
      }}
    >
      Analytics choice
    </button>
  );
}
