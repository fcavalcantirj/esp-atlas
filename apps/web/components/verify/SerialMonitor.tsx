"use client";

import { useEffect, useRef, useState } from "react";
import { track } from "@/lib/analytics";
import { friendlySerialError } from "@/lib/serial-errors";

// Rail B (SPEC-verify.md "Serial monitor"): plain Web Serial, decoded text
// streamed into a scrollable console. No esptool-js here — this rail never
// speaks the ROM protocol, it just reads whatever the firmware already wrote
// to UART.
//
// The connect troubleshooter is intentionally NOT rendered here: VerifyBoard
// (which mounts this monitor on both /debug and /parts/[id]) owns the single
// troubleshooter for the page, so an error in both rails never stacks two.
const BAUD_RATES = [9600, 74880, 115200, 921600];
// Keeps a long-running session's console from growing without bound.
const MAX_LINES = 2000;

export default function SerialMonitor() {
  const [baud, setBaud] = useState(115200);
  const [connected, setConnected] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const portRef = useRef<SerialPort | null>(null);
  const readerRef = useRef<ReadableStreamDefaultReader<string> | null>(null);
  // The port.readable -> decoder pipe; disconnect must await it before close().
  const readableClosedRef = useRef<Promise<void> | null>(null);
  const closingRef = useRef(false);
  const consoleRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const el = consoleRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  // Release the port when the panel unmounts (navigating away) while connected,
  // so a lingering open port never starves the flasher. Refs are stable, so the
  // cleanup captured at mount closes over the live port.
  useEffect(() => {
    return () => {
      void disconnect();
    };
  }, []);

  async function readLoop(port: SerialPort) {
    if (!port.readable) return;
    const decoder = new TextDecoderStream();
    // Keep the pipe promise so disconnect() can wait for the readable lock to
    // release before it closes the port.
    const readableClosed = port.readable.pipeTo(decoder.writable as WritableStream<Uint8Array>).catch(() => {});
    readableClosedRef.current = readableClosed;
    const reader = decoder.readable.getReader();
    readerRef.current = reader;
    let buffer = "";
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        if (!value) continue;
        buffer += value;
        const parts = buffer.split("\n");
        buffer = parts.pop() ?? "";
        if (parts.length > 0) setLines((prev) => [...prev, ...parts].slice(-MAX_LINES));
      }
    } catch {
      if (!closingRef.current) setError("Lost the serial connection — the device may have been unplugged.");
    } finally {
      reader.releaseLock();
      readerRef.current = null;
      if (!closingRef.current) setConnected(false);
    }
  }

  async function connect() {
    setError(null);
    if (!("serial" in navigator)) {
      setError("Web Serial needs Chrome or Edge on a desktop.");
      return;
    }
    let port: SerialPort;
    try {
      port = await navigator.serial.requestPort();
    } catch {
      return; // user dismissed the port picker — not an error
    }
    try {
      await port.open({ baudRate: baud });
    } catch (err) {
      setError(friendlySerialError(err, "Could not open the serial port — is it in use by another program?"));
      return;
    }
    closingRef.current = false;
    portRef.current = port;
    setConnected(true);
    track("monitor_connect", { baud });
    void readLoop(port);
  }

  async function disconnect() {
    closingRef.current = true;
    track("monitor_disconnect", {});
    try {
      await readerRef.current?.cancel();
    } catch {
      // already gone
    }
    // Wait for the readable-stream pipe to finish so the port's lock is released
    // before we close it; closing a still-locked port throws and leaks the port.
    try {
      await readableClosedRef.current;
    } catch {
      // already settled
    }
    try {
      await portRef.current?.close();
    } catch {
      // already gone
    }
    portRef.current = null;
    readerRef.current = null;
    readableClosedRef.current = null;
    setConnected(false);
  }

  return (
    <div className="verify-monitor">
      <div className="verify-monitor-controls">
        <label className="verify-monitor-baud">
          Baud
          <select value={baud} onChange={(e) => setBaud(Number(e.target.value))} disabled={connected}>
            {BAUD_RATES.map((rate) => (
              <option key={rate} value={rate}>
                {rate}
              </option>
            ))}
          </select>
        </label>
        {connected ? (
          <button type="button" className="btn btn--sm" onClick={() => void disconnect()}>
            Disconnect
          </button>
        ) : (
          <button type="button" className="btn btn--sm" onClick={() => void connect()}>
            Connect
          </button>
        )}
        <button type="button" className="btn btn--sm" onClick={() => setLines([])} disabled={lines.length === 0}>
          Clear
        </button>
      </div>
      {error && <p className="verify-error">{error}</p>}
      <pre className="verify-console" ref={consoleRef} aria-live="polite" aria-label="Serial monitor output">
        {lines.length > 0 ? lines.join("\n") : connected ? "Connected — waiting for output…" : "Not connected."}
      </pre>
    </div>
  );
}
