"use client";

// The analytics consent banner for visitors in the EEA, the UK and Switzerland (lib/consent.ts). Until they
// choose, Consent Mode keeps analytics cookies off there (the boot script's default). Shown only when no
// choice is stored and /api/consent-region says the region needs one; the footer's "Analytics choice" link
// clears the choice and brings it back.
import { useCallback, useEffect, useState } from "react";
import { CONSENT_KEY, applyConsent, bannerVisible, parseStoredConsent } from "@/lib/consent";

export const CONSENT_RESET_EVENT = "esp-atlas:consent-reset";

function storedChoice() {
  try {
    return parseStoredConsent(window.localStorage.getItem(CONSENT_KEY));
  } catch {
    return null;
  }
}

export default function ConsentBanner() {
  const [show, setShow] = useState(false);

  const check = useCallback(() => {
    if (storedChoice() !== null) return;
    fetch("/api/consent-region", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : { consent_required: true }))
      .then((d: { consent_required?: boolean }) => setShow(bannerVisible(storedChoice(), d.consent_required !== false)))
      .catch(() => setShow(bannerVisible(storedChoice(), true)));      // unknown: ask rather than assume
  }, []);

  useEffect(() => {
    check();
    window.addEventListener(CONSENT_RESET_EVENT, check);
    return () => window.removeEventListener(CONSENT_RESET_EVENT, check);
  }, [check]);

  if (!show) return null;
  const choose = (choice: "granted" | "denied") => {
    applyConsent(choice);
    setShow(false);
  };
  return (
    <section className="consent-banner" aria-label="Analytics consent">
      <p>
        esp-atlas uses Google Analytics cookies to learn which pages help people find and flash the right board. They
        stay off until you choose.
      </p>
      <div className="consent-banner-actions">
        {/* Equal weight for both choices: no nudging toward accept. */}
        <button type="button" className="btn" onClick={() => choose("granted")}>
          Accept analytics
        </button>
        <button type="button" className="btn" onClick={() => choose("denied")}>
          Decline
        </button>
      </div>
    </section>
  );
}
