// Web Serial `port.open()` (and esptool-js' Transport, which opens the port for
// us) throws a DOMException when the port is already held open — by another
// browser tab, or by the Serial Monitor rail on the same page. The raw message
// ("Failed to execute 'open' on 'SerialPort': The port is already open.") is
// opaque; VerifyBoard and SerialMonitor route their connect errors through this
// so the user gets plain, actionable guidance instead. Pure + no browser
// globals so it is unit-testable under `node --test`.

/** Plain guidance shown when the chosen port is already open elsewhere. */
export const PORT_ALREADY_OPEN_MESSAGE =
  "That serial port is already open in another tab or the Serial Monitor below — disconnect it (or unplug and replug the board), then try again.";

/** True when the thrown value is the "port already open" failure. */
export function isPortAlreadyOpen(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return err.name === "InvalidStateError" || /already open/i.test(err.message);
}

/**
 * Map a Web Serial connect error to a user-facing message: the friendly
 * "already open" guidance when that is what failed, otherwise `fallback`.
 */
export function friendlySerialError(err: unknown, fallback: string): string {
  return isPortAlreadyOpen(err) ? PORT_ALREADY_OPEN_MESSAGE : fallback;
}
