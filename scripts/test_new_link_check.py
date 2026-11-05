"""Tests for scripts/new_link_check.py — the blocking check on URLs a PR adds or changes.

Everything is local: a fake HTTP server on 127.0.0.1 answers with scripted statuses, and each
end-to-end test builds a throwaway git repo (main + a PR branch) so the diff is real.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import new_link_check as nlc  # noqa: E402


# --- the fake server -----------------------------------------------------------------------

class FakeServer:
    """routes: {path: {"GET": [status, ...], "HEAD": [...], "sleep": seconds}}. The last status
    in a list repeats; an unknown path answers 200. Every request is logged in `hits`."""

    def __init__(self, routes):
        self.routes, self.hits, self._lock = routes, [], threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self):
                with fake._lock:
                    fake.hits.append((self.command, self.path))
                    n = sum(1 for h in fake.hits if h == (self.command, self.path))
                route = fake.routes.get(self.path, {})
                time.sleep(route.get("sleep", 0))
                statuses = route.get(self.command, [200])
                self.send_response(statuses[min(n, len(statuses)) - 1])
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_HEAD = _answer

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.httpd.block_on_close = False
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def url(self, path):
        return self.base + path

    def hit(self, path):
        return [m for m, p in self.hits if p == path]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


ROUTES = {
    "/ok": {},
    "/gone404": {"GET": [404], "HEAD": [404]},
    "/gone410": {"GET": [410], "HEAD": [410]},
    "/down503": {"GET": [503], "HEAD": [503]},
    "/ratelimited": {"GET": [429], "HEAD": [429]},
    "/botwall": {"GET": [403], "HEAD": [403]},
    "/slow": {"sleep": 2.0},
    "/flaky": {"HEAD": [405], "GET": [404, 200]},
    "/flaky503": {"HEAD": [405], "GET": [404, 503]},
    "/head-refused": {"HEAD": [405], "GET": [200]},
}


@pytest.fixture
def server():
    s = FakeServer(ROUTES)
    yield s
    s.close()


FAST = dict(timeout=0.5, recheck_delay=0)


# --- a throwaway repo ----------------------------------------------------------------------

def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", *args], cwd=repo, check=True, capture_output=True)


BOARD = "data/boards/acme/acme-one/board.md"


def board_md(*urls, note="x"):
    sources = "".join(f"- field: '*'\n  url: {u}\n  verified: '2026-11-04'\n" for u in urls)
    return f"---\nid: acme-one\ntype: board\nnotes:\n- {note}\nsources:\n{sources}---\n\n# Acme One\n"


def make_repo(tmp_path, main_files, pr_files):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    for files in (main_files, pr_files):
        for rel, text in files.items():
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "--allow-empty", "-m", "c")
        if files is main_files:
            git(repo, "checkout", "-q", "-b", "pr")
    return repo


def run(repo, *extra):
    return nlc.main(["--repo", str(repo), "--base", "main", "--timeout", "0.5", "--recheck-delay", "0", *extra])


# --- the owner rule, end to end ------------------------------------------------------------

def test_an_added_404_link_fails_the_pr(tmp_path, server, capsys):
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/ok"))},
                     {BOARD: board_md(server.url("/ok"), server.url("/gone404"))})
    assert run(repo) == 1
    out = capsys.readouterr().out
    assert "DEAD" in out and server.url("/gone404") in out


def test_an_added_410_link_fails_the_pr(tmp_path, server):
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/ok"))},
                     {BOARD: board_md(server.url("/ok"), server.url("/gone410"))})
    assert run(repo) == 1


def test_an_added_503_link_is_inconclusive_and_passes(tmp_path, server, capsys):
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/ok"))},
                     {BOARD: board_md(server.url("/ok"), server.url("/down503"))})
    assert run(repo) == 0
    assert "INCONCLUSIVE" in capsys.readouterr().out


def test_an_added_link_that_times_out_is_inconclusive_and_passes(tmp_path, server, capsys):
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/ok"))},
                     {BOARD: board_md(server.url("/ok"), server.url("/slow"))})
    assert run(repo) == 0
    assert "INCONCLUSIVE" in capsys.readouterr().out


def test_an_unchanged_link_already_dead_on_main_is_not_even_checked(tmp_path, server):
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/gone404"))},
                     {BOARD: board_md(server.url("/gone404"), server.url("/ok"))})
    assert run(repo) == 0
    assert server.hit("/gone404") == []
    assert server.hit("/ok") != []


def test_a_changed_line_that_keeps_the_same_dead_url_counts_as_changed(tmp_path, server):
    before = f"---\nid: acme-one\n---\n\nSee [the datasheet]({server.url('/gone404')}).\n"
    after = f"---\nid: acme-one\n---\n\nSee [the official datasheet]({server.url('/gone404')}).\n"
    repo = make_repo(tmp_path, {BOARD: before}, {BOARD: after})
    assert run(repo) == 1


def test_a_404_then_200_on_recheck_is_alive(tmp_path, server, capsys):
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/ok"))},
                     {BOARD: board_md(server.url("/ok"), server.url("/flaky"))})
    assert run(repo) == 0
    assert server.hit("/flaky").count("GET") == 2
    assert "DEAD" not in capsys.readouterr().out


def test_links_outside_data_are_not_this_gates_business(tmp_path, server):
    repo = make_repo(tmp_path, {"README.md": "hi\n"},
                     {"README.md": f"hi {server.url('/gone404')}\n"})
    assert run(repo) == 0
    assert server.hit("/gone404") == []


def test_a_bad_base_ref_fails_closed(tmp_path, server, capsys):
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/ok"))}, {})
    assert nlc.main(["--repo", str(repo), "--base", "no-such-ref"]) == 2
    assert "::error::" in capsys.readouterr().out


def test_dead_links_are_annotated_with_file_and_line(tmp_path, server, capsys):
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/ok"))},
                     {BOARD: board_md(server.url("/ok"), server.url("/gone404"))})
    run(repo)
    assert f"::error file={BOARD},line=11::" in capsys.readouterr().out


# --- classification ------------------------------------------------------------------------

@pytest.mark.parametrize("path,status", [
    ("/ok", "alive"),
    ("/head-refused", "alive"),
    ("/gone404", "dead"),
    ("/gone410", "dead"),
    ("/down503", "inconclusive"),
    ("/ratelimited", "inconclusive"),
    ("/botwall", "inconclusive"),
    ("/slow", "inconclusive"),
    ("/flaky", "alive"),
    ("/flaky503", "inconclusive"),
])
def test_check_url_classification(server, path, status):
    assert nlc.check_url(server.url(path), **FAST)[0] == status


def test_a_dead_verdict_takes_two_gets(server):
    nlc.check_url(server.url("/gone404"), **FAST)
    assert server.hit("/gone404") == ["HEAD", "GET", "GET"]


def test_an_alive_head_needs_no_get(server):
    nlc.check_url(server.url("/ok"), **FAST)
    assert server.hit("/ok") == ["HEAD"]


def test_a_refused_connection_is_inconclusive(server):
    port = server.httpd.server_address[1]
    server.close()
    assert nlc.check_url(f"http://127.0.0.1:{port}/x", **FAST)[0] == "inconclusive"


def test_check_all_dedupes_and_respects_the_concurrency_cap(server):
    urls = [server.url(f"/ok?{i}") for i in range(6)]
    results = nlc.check_all(urls, concurrency=2, **FAST)
    assert set(results) == set(urls)
    assert all(v[0] == "alive" for v in results.values())


# --- diff parsing and URL extraction -------------------------------------------------------

DIFF = """\
diff --git a/data/boards/a/b/board.md b/data/boards/a/b/board.md
index 1..2 100644
--- a/data/boards/a/b/board.md
+++ b/data/boards/a/b/board.md
@@ -3 +3,2 @@
-  url: https://old.example/x
+  url: https://new.example/x
+++ this content line starts with two pluses https://plus.example/y
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
+https://readme.example/
diff --git a/data/firmware/f/signals.json b/data/firmware/f/signals.json
--- a/data/firmware/f/signals.json
+++ b/data/firmware/f/signals.json
@@ -10,0 +11 @@
+      "url": "https://github.com/o/r/blob/dev/platformio.ini#L285",
diff --git a/data/boards/a/b/photo.png b/data/boards/a/b/photo.png
--- /dev/null
+++ b/data/boards/a/b/photo.png
@@ -0,0 +1 @@
+https://binary.example/
"""


def test_added_lines_keep_only_data_text_files_with_new_line_numbers():
    assert nlc.added_lines(DIFF) == [
        ("data/boards/a/b/board.md", 3, "  url: https://new.example/x"),
        ("data/boards/a/b/board.md", 4, "++ this content line starts with two pluses https://plus.example/y"),
        ("data/firmware/f/signals.json", 11, '      "url": "https://github.com/o/r/blob/dev/platformio.ini#L285",'),
    ]


@pytest.mark.parametrize("line,urls", [
    ("  url: https://a.example/p", ["https://a.example/p"]),
    ("See [x](https://a.example/p). And <https://b.example/q>,", ["https://a.example/p", "https://b.example/q"]),
    ('"vendor_url": "http://a.example/p?x=1",', ["http://a.example/p?x=1"]),
    ("- 'https://a.example/p' quoted", ["https://a.example/p"]),
    ("[wiki](https://en.wikipedia.org/wiki/Foo_(bar))", ["https://en.wikipedia.org/wiki/Foo_(bar)"]),
    ("no links here", []),
])
def test_urls_in_a_line(line, urls):
    assert nlc.urls_in(line) == urls


def test_extract_urls_dedupes_ignoring_the_fragment_and_keeps_every_location():
    found = nlc.extract_urls([
        ("a.md", 1, "url: https://a.example/p#L1"),
        ("b.md", 7, "url: https://a.example/p#L2"),
    ])
    assert found == {"https://a.example/p": [("a.md", 1), ("b.md", 7)]}
