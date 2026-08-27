"""EspAtlas Jr — outbound Telegram nudges (§7).

Reuses the box's existing Telegram bot (token + home channel from ~/.hermes/.env) so Jr can
reach Felipe with PR nudges, dead-source alerts, and the weekly digest. A later step can give
Jr its own @BotFather bot; the interface here doesn't change.
"""
from __future__ import annotations
import json
import os
import urllib.request
from pathlib import Path


def _load_env() -> None:
    for envfile in (Path.home() / ".config/jr/keys.env", Path.home() / ".hermes/.env"):
        if not envfile.exists():
            continue
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def send_telegram(text: str) -> dict:
    """Send a Markdown message to Jr's Telegram home channel. Returns {"ok": bool}."""
    _load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_HOME_CHANNEL") or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return {"ok": False, "error": "no TELEGRAM_BOT_TOKEN / TELEGRAM_HOME_CHANNEL"}
    payload = json.dumps({"chat_id": chat, "text": text,
                          "parse_mode": "Markdown", "disable_web_page_preview": False}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return {"ok": json.load(r).get("ok", False)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def nudge_pr(firmware_id: str, name: str, pr_url: str, board: str) -> dict:
    """The PR nudge Jr fires when it proposes a record."""
    return send_telegram(
        f"🤖 *Jr proposed a PR* — [{name}]({pr_url})\n"
        f"`{firmware_id}` → board `{board}` · `unverified` · triple-validated ✓\n"
        f"Your review + merge, when you like."
    )


if __name__ == "__main__":
    r = send_telegram(
        "🤖 *Jr nudge — live test*\n"
        "First contribution [#69 Evil-M5Project](https://esp-atlas.com/firmware/evil-m5project) "
        "is *merged & live* (guard 188/188). This is the nudge you'll get on every future PR."
    )
    print("send:", r)
