"""ask(question) -> {answer, citations, used} — retrieval + grounded Groq answer.

Retrieval and citations are entirely deterministic (esp_atlas_core.search);
only the prose answer comes from the LLM, and it is grounded by construction:
the prompt is built from prompts/system.md plus the full markdown of the
top-K retrieved records, at temperature 0. Citations are derived directly
from those records' own `sources`, never parsed out of the LLM's reply, so
`ask()` always returns citations even if the model forgets to mention them.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from esp_atlas_core import db as dbmod
from esp_atlas_core.firmware import list_firmware, recipes_for_board, recipes_for_firmware
from esp_atlas_core.llm import GroqClient
from esp_atlas_core.paths import PROMPTS_DIR, REPO_ROOT
from esp_atlas_core.search import get_part, search

NOT_FOUND_ANSWER = "That's not in esp-atlas yet — you can add it with a pull request."
DEFAULT_TOP_K = 5

# "Which boards run Marauder?" is the home's lead intent, but firmware and
# recipes are deliberately absent from the parts table and the FTS index (they
# are first-class entities, like brands), so plain retrieval cannot see them and
# the honest answer used to be "not in esp-atlas yet" -- while the site's own
# firmware pages listed the boards. Retrieval therefore gets a second, explicit
# path over the recipe graph, leaving the table/index boundary untouched.
#
# Tokens too generic to identify a project: every record mentions them.
_FIRMWARE_STOPWORDS = frozenset({"esp32", "esp", "m5", "the", "for", "and", "run", "runs"})
_MIN_FIRMWARE_TOKEN = 4


def _cache_key(question, build_id):
    normalized = question.strip().lower()
    return hashlib.sha256(f"{build_id}:{normalized}".encode("utf-8")).hexdigest()


def _get_build_id(db_path):
    conn = dbmod.connect(db_path)
    try:
        try:
            return dbmod.get_meta(conn, "build_id")
        except sqlite3.OperationalError as exc:
            raise RuntimeError(
                "esp-atlas.db has no index yet — run esp_atlas_core.index_build.build_index() first."
            ) from exc
    finally:
        conn.close()


def _read_cache(db_path, cache_key):
    conn = dbmod.connect(db_path)
    try:
        row = conn.execute(
            "SELECT answer, citations_json, used_json FROM answer_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "answer": row["answer"],
        "citations": json.loads(row["citations_json"]),
        "used": json.loads(row["used_json"]),
    }


def _write_cache(db_path, cache_key, build_id, question, result):
    conn = dbmod.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO answer_cache (cache_key, build_id, question, answer, citations_json, used_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                answer = excluded.answer,
                citations_json = excluded.citations_json,
                used_json = excluded.used_json,
                created_at = excluded.created_at
            """,
            (
                cache_key,
                build_id,
                question,
                result["answer"],
                json.dumps(result["citations"]),
                json.dumps(result["used"]),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _firmware_keys(fw):
    """The strings that identify this firmware in a question."""
    keys = {fw["id"].lower(), fw["name"].lower()}
    for token in fw["name"].lower().replace("-", " ").split():
        if len(token) >= _MIN_FIRMWARE_TOKEN and token not in _FIRMWARE_STOPWORDS:
            keys.add(token)
    return {k for k in keys if k not in _FIRMWARE_STOPWORDS}


def _firmware_named_in(question):
    """Firmware the question actually names — 'run Marauder' -> the Marauder record."""
    haystack = question.lower()
    return [fw for fw in list_firmware() if any(key in haystack for key in _firmware_keys(fw))]


def _board_label(board_id, db_path):
    part = get_part(board_id, db_path=db_path)
    return part["name"] if part else board_id


def _runs_on_block(fw, db_path):
    """The recipe graph for one firmware, as facts the model can quote."""
    recipes = recipes_for_firmware(fw["id"])
    if not recipes:
        return None
    lines = [
        f"Firmware: {fw['name']} (id: {fw['id']}, category: {fw.get('category', 'unknown')})",
        f"Project URL: {fw.get('url', 'unknown')}",
        f"Runs on these {len(recipes)} board(s) in esp-atlas, with the trust tier of each claim:",
    ]
    for recipe in sorted(recipes, key=lambda r: r["board"]):
        lines.append(f"- {_board_label(recipe['board'], db_path)} (id: {recipe['board']}) [{recipe['status']}]")
    return "\n".join(lines)


def _board_runs_block(part, db_path):
    """The reverse view: what a retrieved board can run."""
    recipes = recipes_for_board(part["id"])
    if not recipes:
        return None
    by_id = {fw["id"]: fw for fw in list_firmware()}
    lines = [f"Firmware verified to run on {part['name']} (id: {part['id']}):"]
    for recipe in sorted(recipes, key=lambda r: r["firmware"]):
        fw = by_id.get(recipe["firmware"], {})
        lines.append(f"- {fw.get('name', recipe['firmware'])} [{recipe['status']}]")
    return "\n".join(lines)


def _recipe_context(question, records, db_path):
    """Recipe-graph facts for the question, plus the ids and sources behind them."""
    blocks, used, citations = [], [], []
    seen = set()

    for fw in _firmware_named_in(question):
        block = _runs_on_block(fw, db_path)
        if not block:
            continue
        blocks.append(block)
        used.append(fw["id"])
        seen.add(fw["id"])
        for source in fw.get("sources") or []:
            citations.append({"part": fw["name"], "file": f"data/firmware/{fw['id']}/firmware.md", "source_url": source["url"]})
        for recipe in recipes_for_firmware(fw["id"]):
            used.append(recipe["id"])

    for part in records:
        if part["type"] != "board":
            continue
        block = _board_runs_block(part, db_path)
        if block:
            blocks.append(block)

    return blocks, used, citations


def _build_citations(records):
    citations = []
    for rec in records:
        for source in rec["sources"]:
            citations.append({"part": rec["name"], "file": rec["_path"], "source_url": source["url"]})
    return citations


def _build_prompt(question, records, recipe_blocks=()):
    parts = [(REPO_ROOT / rec["_path"]).read_text(encoding="utf-8") for rec in records]
    context = "\n\n---\n\n".join(parts + list(recipe_blocks))
    return f"Context (esp-atlas dataset records — frontmatter + prose, each with sources):\n\n{context}\n\nQuestion: {question}"


def ask(question, llm_client=None, db_path=None, top_k=DEFAULT_TOP_K):
    build_id = _get_build_id(db_path)
    cache_key = _cache_key(question, build_id)

    cached = _read_cache(db_path, cache_key)
    if cached is not None:
        return cached

    records = search(question, filters={}, db_path=db_path, limit=top_k)
    recipe_blocks, recipe_used, recipe_citations = _recipe_context(question, records, db_path)
    if not records and not recipe_blocks:
        result = {"answer": NOT_FOUND_ANSWER, "citations": [], "used": []}
        _write_cache(db_path, cache_key, build_id, question, result)
        return result

    system_prompt = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
    user_prompt = _build_prompt(question, records, recipe_blocks)

    client = llm_client or GroqClient()
    answer = client.complete(system_prompt, user_prompt, temperature=0)

    result = {
        "answer": answer,
        "citations": _build_citations(records) + recipe_citations,
        "used": [rec["id"] for rec in records] + recipe_used,
    }
    _write_cache(db_path, cache_key, build_id, question, result)
    return result
