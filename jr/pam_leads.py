"""Unverified PAM discovery leads, never catalog facts (SPEC-pam-discovery.md).

The caller owns its existing job/lock, atomic persistence, demand-first budget,
primary-source research and reviewed publication. This module does none of those
implicitly. Feed values, marketing and affiliate links are not exported.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import datetime as dt
import hashlib
import ipaddress
import json
import re
from urllib import error, request
from urllib.parse import urlsplit


ENDPOINTS = {name: f"https://pamfinds.com/api/{name}.json" for name in ("products", "specs")}
MAX_BYTES = 524_288
MAX_PRODUCTS = 500
TIMEOUT_SECONDS = 15
VERSION = 1
_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_ESP = re.compile(r"^(ESP32(?:-[A-Z]\d{1,2})?|ESP8266)(?=$|[^A-Z0-9])", re.I)


class FeedError(ValueError):
    """Refresh failed; the caller must retain last-good state and report the error."""


@dataclass(frozen=True)
class FeedReply:
    status: int
    payload: dict | None = None
    etag: str | None = None
    sha256: str | None = None
    size: int = 0


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = request.build_opener(_NoRedirect)


def fetch_feed(name: str, etag: str | None = None) -> FeedReply:
    """GET one fixed public endpoint; no credentials or source-pointer fetching."""
    if name not in ENDPOINTS:
        raise FeedError("unknown feed endpoint")
    headers = {"Accept": "application/json", "User-Agent": "esp-atlas-jr/discovery"}
    if etag:
        if not isinstance(etag, str) or len(etag) > 256 or any(c in etag for c in "\r\n"):
            raise FeedError("invalid cached ETag")
        headers["If-None-Match"] = etag
    try:
        req = request.Request(ENDPOINTS[name], headers=headers)
        with _OPENER.open(req, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise FeedError(f"{name}: unexpected HTTP status {response.status}")
            if "application/json" not in response.headers.get("Content-Type", "").lower():
                raise FeedError(f"{name}: expected JSON content type")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise FeedError(f"{name}: feed exceeds size bound")
            payload = json.loads(raw)
            new_etag = response.headers.get("ETag")
            if new_etag and (len(new_etag) > 256 or any(c in new_etag for c in "\r\n")):
                raise FeedError(f"{name}: invalid response ETag")
            return FeedReply(200, payload, new_etag, hashlib.sha256(raw).hexdigest(), len(raw))
    except error.HTTPError as exc:
        if exc.code == 304:
            return FeedReply(304)
        raise FeedError(f"{name}: HTTP {exc.code}") from exc
    except (OSError, ValueError) as exc:
        if isinstance(exc, FeedError):
            raise
        raise FeedError(f"{name}: unreadable feed ({type(exc).__name__})") from exc


def _text(value, *, limit=160) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise FeedError("missing or oversized identity hint")
    if any(ord(c) < 32 for c in value):
        raise FeedError("control character in identity hint")
    return value.strip()


def _pointer(value) -> str | None:
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() for c in value):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (parsed.scheme != "https" or not host or parsed.username or parsed.password
                or parsed.port not in (None, 443) or host == "localhost"
                or host.endswith((".localhost", ".local"))):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            if "." not in host:
                return None
        return value
    except ValueError:
        return None


def _index(payload) -> dict:
    if not isinstance(payload, dict):
        raise FeedError("feed root is not an object")
    rows = payload.get("products")
    count = payload.get("count")
    if (not isinstance(rows, list) or not 0 < len(rows) <= MAX_PRODUCTS
            or type(count) is not int or count != len(rows)):
        raise FeedError("unreadable or inconsistent product count")
    indexed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise FeedError("unreadable product row")
        key = _text(row.get("id"), limit=100)
        if not _ID.fullmatch(key) or key in indexed:
            raise FeedError("invalid or duplicate source ID")
        indexed[key] = row
    return indexed


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _minimal_leads(products, specs) -> list[dict]:
    p, s = _index(products), _index(specs)
    if p.keys() != s.keys():
        raise FeedError("product/spec source IDs do not match")
    leads = []
    for source_id, product in sorted(p.items()):
        fields = s[source_id].get("specs")
        if not isinstance(fields, dict) or len(fields) > 128:
            raise FeedError("unreadable spec field map")
        chip = product.get("chip")
        family = _ESP.match(chip) if isinstance(chip, str) else None
        if not family:
            continue
        name = _text(product.get("name"))
        page = _pointer(product.get("page"))
        if not page or urlsplit(page).hostname != "pamfinds.com":
            raise FeedError("missing or invalid lead page")
        pointers = {}
        for field, info in fields.items():
            if not isinstance(field, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,63}", field):
                raise FeedError("invalid field name")
            if not isinstance(info, dict):
                raise FeedError("unreadable field pointer")
            url = _pointer(info.get("source"))
            if url:
                pointers[field] = [url]
        lead = {"source_id": source_id, "name_hint": name, "chip_hint": family[1].upper(),
                "page": page, "source_pointers": pointers}
        lead["fingerprint"] = _hash(lead)
        leads.append(lead)
    return leads


def _label(value) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold()) if isinstance(value, str) else ""


def _classify(leads: list[dict], catalog: list[dict]) -> list[dict]:
    labels = {}
    for record in catalog:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise FeedError("unreadable catalog identity")
        aliases = []
        for field in ("aka", "aliases"):
            value = record.get(field, [])
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise FeedError("unreadable catalog alias list")
            aliases.extend(value)
        for value in [record["id"], record.get("name"), *aliases]:
            label = _label(value)
            if label:
                labels.setdefault(label, set()).add(record["id"])
    result = copy.deepcopy(leads)
    for lead in result:
        matches = labels.get(_label(lead["source_id"]), set()) | labels.get(_label(lead["name_hint"]), set())
        lead["matches"] = sorted(matches)
        lead["status"] = ("ambiguous_match" if len(matches) > 1 else "possible_match" if matches
                          else "potential_identity_gap")
    return result


def _previous(state) -> None:
    if state is None:
        return
    if (not isinstance(state, dict) or state.get("version") != VERSION or state.get("source") != "pam_feed"
            or not isinstance(state.get("leads"), list) or not isinstance(state.get("feeds"), dict)):
        raise FeedError("corrupt cached PAM state")
    try:
        if dt.datetime.fromisoformat(state["checked_at"]).tzinfo is None:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise FeedError("corrupt cached check timestamp") from None
    for name, url in ENDPOINTS.items():
        meta = state["feeds"].get(name)
        if (not isinstance(meta, dict) or meta.get("url") != url
                or not isinstance(meta.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", meta["sha256"])
                or type(meta.get("bytes")) is not int or not 0 < meta["bytes"] <= MAX_BYTES):
            raise FeedError("corrupt cached feed provenance")
        try:
            if dt.datetime.fromisoformat(meta["fetched_at"]).tzinfo is None:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise FeedError("corrupt cached feed timestamp") from None
    fields = {"source_id", "name_hint", "chip_hint", "page", "source_pointers"}
    seen = set()
    for lead in state["leads"]:
        if (not isinstance(lead, dict) or not fields | {"fingerprint", "matches", "status"} <= lead.keys()
                or not lead.keys() <= fields | {"fingerprint", "matches", "status"}
                or not isinstance(lead["source_id"], str) or not _ID.fullmatch(lead["source_id"])
                or lead["source_id"] in seen or not isinstance(lead["source_pointers"], dict)
                or _pointer(lead["page"]) != lead["page"]
                or urlsplit(lead["page"]).hostname != "pamfinds.com"
                or lead.get("fingerprint") != _hash({k: lead[k] for k in fields})
                or lead["status"] not in ("possible_match", "ambiguous_match", "potential_identity_gap")
                or not isinstance(lead["matches"], list)
                or not all(isinstance(x, str) and x for x in lead["matches"])):
            raise FeedError("corrupt cached lead")
        _text(lead["name_hint"])
        _text(lead["chip_hint"])
        for pointers in lead["source_pointers"].values():
            if not isinstance(pointers, list) or not pointers or any(_pointer(p) != p for p in pointers):
                raise FeedError("corrupt cached source pointer")
        seen.add(lead["source_id"])


def refresh(previous: dict | None, catalog: list[dict], *, now: dt.datetime,
            fetch=fetch_feed) -> dict:
    """Return replacement minimal state only on a complete valid refresh; never mutate inputs.

    Exceptions leave the caller's last-good state intact. The caller must persist
    atomically under its existing lock. Both 304s still recheck the current catalog.
    """
    _previous(previous)
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise FeedError("refresh requires an aware UTC timestamp")
    stamp = now.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    old_meta = previous["feeds"] if previous else {}
    replies = {name: fetch(name, old_meta.get(name, {}).get("etag")) for name in ENDPOINTS}
    if any(r.status not in (200, 304) for r in replies.values()):
        raise FeedError("unexpected feed status")
    unchanged = all(r.status == 304 for r in replies.values())
    if unchanged:
        if previous is None:
            raise FeedError("304 without last-good lead state")
        leads, metadata = previous["leads"], old_meta
    else:
        for name, response in list(replies.items()):
            if response.status == 304:
                replies[name] = fetch(name, None)
        if any(r.status != 200 for r in replies.values()):
            raise FeedError("incomplete unconditional feed refresh")
        leads = _minimal_leads(replies["products"].payload, replies["specs"].payload)
        metadata = {}
        for name, response in replies.items():
            if (not isinstance(response.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", response.sha256)
                    or not 0 < response.size <= MAX_BYTES):
                raise FeedError("unreadable feed provenance")
            metadata[name] = {"url": ENDPOINTS[name], "fetched_at": stamp, "etag": response.etag,
                              "sha256": response.sha256, "bytes": response.size}
    return {"version": VERSION, "source": "pam_feed", "checked_at": stamp,
            "feeds": copy.deepcopy(metadata), "leads": _classify(leads, catalog)}


def candidate_leads(state: dict, *, handled_keys=()) -> list[dict]:
    """Unmatched identities for research, not authoring. Caller applies shared global caps.

    Reconcile prior work/outcomes by stable key and exact target before creating
    anything. Feed timestamps/hashes do not change work identity. No GA metrics or
    fabricated search date window are attached to these market leads.
    """
    _previous(state)
    if state is None:
        raise FeedError("missing PAM state")
    handled = set(handled_keys)
    candidates = []
    for lead in state["leads"]:
        key = work_key(lead)
        if lead["status"] != "potential_identity_gap" or key in handled:
            continue
        candidates.append({"key": key, "source": "pam_feed", "source_id": lead["source_id"],
                           "name_hint": lead["name_hint"], "chip_hint": lead["chip_hint"],
                           "phase": "research", "identity_verified": False,
                           "source_pointers": copy.deepcopy(lead["source_pointers"]), "page": lead["page"],
                           "provenance": {"checked_at": state["checked_at"],
                                          "feeds": copy.deepcopy(state["feeds"])}})
    return candidates


def work_key(lead: dict) -> str:
    """Semantic feed identity, unaffected by fetch time, HTTP receipt or catalog match."""
    return "pam-" + _hash([lead["source_id"], lead["fingerprint"]])[:24]


def readable_work_provenance(value) -> bool:
    """Validate the original minimal feed snapshot without fetching anything."""
    if not isinstance(value, dict) or set(value) != {"lead", "checked_at", "feeds"}:
        return False
    feeds = value["feeds"]
    fields = {"url", "fetched_at", "etag", "sha256", "bytes"}
    if (not isinstance(feeds, dict) or set(feeds) != set(ENDPOINTS)
            or any(not isinstance(meta, dict) or set(meta) != fields for meta in feeds.values())):
        return False
    try:
        _previous({"version": VERSION, "source": "pam_feed", "leads": [value["lead"]],
                   "checked_at": value["checked_at"], "feeds": value["feeds"]})
    except (FeedError, TypeError, KeyError):
        return False
    return True
