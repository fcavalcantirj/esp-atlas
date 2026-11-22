"""EspAtlas Jr — pinned project trees and vendor-verified platform packages (jr/claims_pio_sources.py).

Jr redesign plan, step 4b (2026-11-22). The network side of jr/claims_pio.py, kept apart so the judge stays pure:

  fetch_project(http, slug, dest)   resolves the default branch to ONE commit first, reads the full git tree at
                                    that commit (a truncated tree, any symlink, or no root platformio.ini is
                                    refused), and writes every *.ini file and boards/*.json manifest into `dest`,
                                    returning their blob shas: the claim's `files`.
  PlatformIndex(http)(spec, board)  the platform_index claims_pio.judge() asks: the pinned platform package,
                                    downloaded once per run and verified against the VENDOR's own published
                                    sha256 (PlatformIO registry checksum for an official version; GitHub's asset
                                    digest for a pioarduino release), then the board manifest read from inside
                                    it. A missing or mismatching digest is None (refused), never trusted.
  board_for(board_id, digest, catalog)
                                    the one catalog board whose cited platformio_definitions list exactly this
                                    (definition id, manifest digest); None when none or several do.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tarfile
import urllib.request
import zipfile
from pathlib import Path

REGISTRY = "https://api.registry.platformio.org/v3/packages/platformio/platform/espressif32"
_OFFICIAL = re.compile(r"^(?:platformio/)?espressif32@(\d+\.\d+\.\d+)$")
_PIOARDUINO = re.compile(r"^https://github\.com/pioarduino/platform-espressif32/releases/download/([\w.\-]+)/platform-espressif32\.zip$")
_KEEP = re.compile(r"(^|/)[^/]+\.ini$|(^|/)boards/[^/]+\.json$")
MAX_FILE = 2 * 1024 * 1024


class Unreadable(Exception):
    pass


class Http:
    """The real transport (GitHub token from GH_TOKEN/GITHUB_TOKEN for api.github.com only)."""

    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    def _get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "esp-atlas-jr"})
        tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if tok and url.startswith("https://api.github.com/"):
            req.add_header("Authorization", f"Bearer {tok}")
            req.add_header("Accept", "application/vnd.github+json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 — every transport failure is the same verdict: unreadable
            raise Unreadable(f"{url}: {e}") from e

    def json(self, url: str):
        return json.loads(self._get(url))

    def bytes(self, url: str) -> bytes:
        return self._get(url)


def fetch_project(http, slug: str, dest: Path) -> dict:
    """{"repo": {slug, id}, "sha", "blobs": {path: blob sha}}; the config files are written under `dest`."""
    meta = http.json(f"https://api.github.com/repos/{slug}")
    branch = meta.get("default_branch")
    if not branch or not isinstance(meta.get("id"), int):
        raise Unreadable(f"{slug}: no default branch or numeric id")
    sha = (http.json(f"https://api.github.com/repos/{slug}/commits/{branch}") or {}).get("sha")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise Unreadable(f"{slug}: could not pin {branch} to a commit")
    return fetch_project_at(http, slug, sha, dest, meta=meta)


def fetch_project_at(http, slug: str, sha: str, dest: Path, meta: dict | None = None) -> dict:
    """fetch_project at a GIVEN commit (the trusted checker re-reads a claim's own commit, never the branch tip)."""
    if not re.fullmatch(r"[0-9a-f]{40}", sha or ""):
        raise Unreadable(f"{slug}: {sha!r} is not a full commit sha")
    meta = meta if meta is not None else http.json(f"https://api.github.com/repos/{slug}")
    if not isinstance(meta.get("id"), int):
        raise Unreadable(f"{slug}: no numeric id")
    tree = http.json(f"https://api.github.com/repos/{slug}/git/trees/{sha}?recursive=1")
    if tree.get("truncated"):
        raise Unreadable(f"{slug}@{sha[:7]}: tree truncated, the config closure cannot be proven complete")
    entries = tree.get("tree") or []
    links = [e["path"] for e in entries if e.get("mode") == "120000"]
    if links:
        raise Unreadable(f"{slug}@{sha[:7]}: symlink in the tree ({', '.join(links[:3])})")
    keep = {e["path"]: e["sha"] for e in entries if e.get("type") == "blob" and _KEEP.search(e["path"])}
    if "platformio.ini" not in keep:
        raise Unreadable(f"{slug}@{sha[:7]}: no platformio.ini at the root")
    dest = Path(dest)
    for path in sorted(keep):
        data = http.bytes(f"https://raw.githubusercontent.com/{slug}/{sha}/{path}")
        if len(data) > MAX_FILE:
            raise Unreadable(f"{slug}@{sha[:7]}: {path} larger than {MAX_FILE} bytes")
        out = (dest / path).resolve()
        if not out.is_relative_to(dest.resolve()):
            raise Unreadable(f"{slug}@{sha[:7]}: path escapes the tree: {path}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    return {"repo": {"slug": meta.get("full_name") or slug, "id": meta["id"]}, "sha": sha, "blobs": keep}


def _verified(data: bytes, published: str | None) -> str | None:
    digest = hashlib.sha256(data).hexdigest()
    return digest if published and published.lower() == digest else None


def _manifest_from(archive: bytes, kind: str, board: str) -> bytes | None:
    want = re.compile(rf"(^|/)boards/{re.escape(board)}\.json$")
    if kind == "tgz":
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as t:
            for m in t.getmembers():
                if m.isfile() and want.search(m.name):
                    return t.extractfile(m).read()
        return None
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        for name in z.namelist():
            if want.search(name) and not name.endswith("/"):
                return z.read(name)
    return None


class PlatformIndex:
    """`(spec, board) -> {"package_digest", "manifest": bytes | None} | None` for claims_pio.judge()."""

    def __init__(self, http):
        self.http, self._pkg = http, {}

    def _package(self, spec: str):
        if spec in self._pkg:
            return self._pkg[spec]
        got = None
        try:
            m = _OFFICIAL.match(spec)
            if m:
                version = m.group(1)
                rel = next((v for v in (self.http.json(REGISTRY).get("versions") or []) if v.get("name") == version), None)
                f = ((rel or {}).get("files") or [{}])[0]
                url, published = f.get("download_url"), (f.get("checksum") or {}).get("sha256")
                if url and published:
                    data = self.http.bytes(url)
                    digest = _verified(data, published)
                    got = (digest, data, "tgz") if digest else None
            m = _PIOARDUINO.match(spec)
            if m:
                rel = self.http.json(f"https://api.github.com/repos/pioarduino/platform-espressif32/releases/tags/{m.group(1)}")
                asset = next((a for a in rel.get("assets") or [] if a.get("name") == "platform-espressif32.zip"), {})
                published = str(asset.get("digest") or "")
                if published.startswith("sha256:"):
                    data = self.http.bytes(spec)
                    digest = _verified(data, published[len("sha256:"):])
                    got = (digest, data, "zip") if digest else None
        except Unreadable:
            got = None
        self._pkg[spec] = got
        return got

    def __call__(self, spec: str, board: str):
        pkg = self._package(spec)
        if pkg is None:
            return None
        digest, data, kind = pkg
        return {"package_digest": digest, "manifest": _manifest_from(data, kind, board)}


def board_for(board_id: str, manifest_digest: str, catalog: dict) -> str | None:
    """`catalog`: {board id: [platformio_definitions entries]}. Exactly one match, or None."""
    hits = [b for b, defs in catalog.items()
            if any(d.get("id") == board_id and d.get("manifest_digest") == manifest_digest for d in defs or [])]
    return hits[0] if len(hits) == 1 else None


def platformio_version() -> str:
    import platformio
    return platformio.__version__


def claim_for(http, slug: str, sha: str, env: str, platform_index, workdir: Path) -> dict:
    """The build-target claim for `env` of `slug` at commit `sha`, exactly as recipes carry it (schema `claim`).
    Raises Unreadable when a source cannot be read and ValueError when the env is refused or absent."""
    import claims_pio as cp
    proj = fetch_project_at(http, slug, sha, Path(workdir))
    resolved = cp.resolve_project(Path(workdir))
    facts, refusals = cp.judge(resolved, platform_index)
    fact = next((f for f in facts if f["env"] == env), None)
    if fact is None:
        why = next((f"{r['rule']}: {r['detail']}" for r in refusals if r["env"] == env), "no such env")
        raise ValueError(f"env {env} is refused ({why})")
    return {"kind": "pio-env", "repo": proj["repo"], "sha": sha, "env": env, "board_id": fact["board_id"],
            "platformio_version": platformio_version(), "platform": fact["platform"],
            "files": [{"path": p, "blob": proj["blobs"][p]} for p in resolved["loaded"]],
            "sections": fact["sections"]}
