"""GET /status computation -- INTERFACE-SPEC.md.

Public, unauthenticated health snapshot computed fresh on every request: no
datastore, no external paid service, no network calls. Each _component_*
probe is independently wrapped by _safe() so one failing probe reports as a
down/warn component instead of raising and crashing the whole response.
"""
import os
from datetime import datetime, timezone

from esp_atlas_core import db as dbmod
from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter

_ENTITY_LABELS = ("soc", "module", "board", "brand", "firmware", "recipe")


def _safe(probe):
    try:
        return probe()
    except Exception as exc:  # a probe failing is data for the page, not a crash
        return {"status": "down", "detail": f"probe failed: {exc}"}


def _component_api(db_path):
    def probe():
        conn = dbmod.connect(db_path)
        try:
            count = dbmod.get_meta(conn, "count")
        finally:
            conn.close()
        if count is None:
            return {"status": "down", "detail": "search index not built"}
        return {"status": "ok", "detail": f"serving, index has {count} records"}

    return {"name": "API", **_safe(probe)}


def _component_data(db_path, data_dir=None):
    def probe():
        counts = dict.fromkeys(_ENTITY_LABELS, 0)
        for content_type, _path in iter_data_files(data_dir):
            counts[content_type] = counts.get(content_type, 0) + 1

        conn = dbmod.connect(db_path)
        try:
            schema_valid = dbmod.get_meta(conn, "build_id") is not None
        finally:
            conn.close()

        counts_text = ", ".join(f"{counts[label]} {label}s" for label in _ENTITY_LABELS)
        detail = f"{counts_text}; schema_valid={'true' if schema_valid else 'false'}"
        status = "ok" if schema_valid and sum(counts.values()) > 0 else "warn"
        return {"status": status, "detail": detail}

    return {"name": "Data", **_safe(probe)}


def _newest_firmware_verified_date(fm):
    """The latest `verified` date across a firmware record's own sources, or
    "" if none of its sources carry one -- see esp_atlas_core.firmware."""
    dates = [str(source["verified"]) for source in (fm.get("sources") or []) if source.get("verified")]
    return max(dates) if dates else ""


def _component_catalog(data_dir=None):
    def probe():
        firmware = [parse_frontmatter(path)[0] for kind, path in iter_data_files(data_dir) if kind == "firmware"]
        if not firmware:
            return {"status": "warn", "detail": "no firmware entries in the catalog"}
        newest = max(firmware, key=lambda fm: (_newest_firmware_verified_date(fm), fm["id"]))
        date = _newest_firmware_verified_date(newest)
        if not date:
            return {"status": "warn", "detail": f"newest: {newest['id']} (no verified date on record)"}
        return {"status": "ok", "detail": f"newest: {newest['id']} (verified {date})"}

    return {"name": "Jr / catalog", **_safe(probe)}


def _component_deploy():
    def probe():
        sha = os.environ.get("VERCEL_GIT_COMMIT_SHA")
        if not sha:
            return {"status": "ok", "detail": "local"}
        parts = [f"commit {sha[:7]}"]
        branch = os.environ.get("VERCEL_GIT_COMMIT_REF")
        env = os.environ.get("VERCEL_ENV")
        if branch:
            parts.append(branch)
        if env:
            parts.append(env)
        return {"status": "ok", "detail": " · ".join(parts)}

    return {"name": "Deploy", **_safe(probe)}


def compute_status(db_path=None, data_dir=None):
    """The full GET /status payload -- see INTERFACE-SPEC.md `GET /status`."""
    components = [
        _component_api(db_path),
        _component_data(db_path, data_dir),
        _component_catalog(data_dir),
        _component_deploy(),
    ]

    api_status = next(c["status"] for c in components if c["name"] == "API")
    if api_status == "down":
        overall = "down"
    elif any(c["status"] in ("warn", "down") for c in components):
        overall = "degraded"
    else:
        overall = "operational"

    return {
        "status": overall,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }
