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
from esp_atlas_core.llm import GroqClient
from esp_atlas_core.paths import PROMPTS_DIR, REPO_ROOT
from esp_atlas_core.search import search

NOT_FOUND_ANSWER = "That's not in esp-atlas yet — you can add it with a pull request."
DEFAULT_TOP_K = 5


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


def _build_citations(records):
    citations = []
    for rec in records:
        for source in rec["sources"]:
            citations.append({"part": rec["name"], "file": rec["_path"], "source_url": source["url"]})
    return citations


def _build_prompt(question, records):
    context = "\n\n---\n\n".join((REPO_ROOT / rec["_path"]).read_text(encoding="utf-8") for rec in records)
    return f"Context (esp-atlas dataset records — frontmatter + prose, each with sources):\n\n{context}\n\nQuestion: {question}"


def ask(question, llm_client=None, db_path=None, top_k=DEFAULT_TOP_K):
    build_id = _get_build_id(db_path)
    cache_key = _cache_key(question, build_id)

    cached = _read_cache(db_path, cache_key)
    if cached is not None:
        return cached

    records = search(question, filters={}, db_path=db_path, limit=top_k)
    if not records:
        result = {"answer": NOT_FOUND_ANSWER, "citations": [], "used": []}
        _write_cache(db_path, cache_key, build_id, question, result)
        return result

    system_prompt = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
    user_prompt = _build_prompt(question, records)

    client = llm_client or GroqClient()
    answer = client.complete(system_prompt, user_prompt, temperature=0)

    result = {
        "answer": answer,
        "citations": _build_citations(records),
        "used": [rec["id"] for rec in records],
    }
    _write_cache(db_path, cache_key, build_id, question, result)
    return result
