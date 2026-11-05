"""Tests for scripts/new_link_check.py — the check on URLs a PR adds or changes.

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
    "/important!": {"GET": [404], "HEAD": [404]},
    "/escaped/gone": {"GET": [404], "HEAD": [404]},
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


def test_a_pure_rename_checks_nothing(tmp_path, server):
    moved = "data/boards/acme/acme-two/board.md"
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/gone404"))}, {})
    (repo / moved).parent.mkdir(parents=True)
    git(repo, "mv", BOARD, moved)
    git(repo, "commit", "-q", "-m", "move")
    assert run(repo) == 0
    assert server.hit("/gone404") == []


def test_a_diff_that_is_not_utf8_does_not_crash_the_job(tmp_path, server):
    raw = b"---\nid: acme-one\nnotes:\n- caf\xe9\n---\n"
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/ok"))}, {})
    (repo / BOARD).write_bytes(raw + f"See {server.url('/ok')}\n".encode())
    git(repo, "commit", "-qam", "latin-1")
    assert run(repo) == 0
    assert server.hit("/ok") != []


def test_a_git_diff_that_hangs_fails_closed_with_a_message(tmp_path, monkeypatch, capsys):
    def hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="git diff", timeout=120)

    monkeypatch.setattr(nlc.subprocess, "run", hang)
    assert nlc.main(["--repo", str(tmp_path), "--base", "main"]) == 2
    assert "::error::" in capsys.readouterr().out


def test_dead_links_are_annotated_with_file_and_line(tmp_path, server, capsys):
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/ok"))},
                     {BOARD: board_md(server.url("/ok"), server.url("/gone404"))})
    run(repo)
    assert f"::error file={BOARD},line=11::" in capsys.readouterr().out


# --- the exact URL the PR adds is the one requested ----------------------------------------
# The fake server records every request path: /important! answers 404 and /important 200, so
# a checker that drops the "!" would wrongly pass, and one that keeps "\\/" would ask for a
# path nobody wrote.

SIGNALS = "data/firmware/acme-fw/signals.json"
SOURCES = "data/boards/acme/acme-one/sources.yml"


def _escaped(url):
    return url.replace("/", "\\/")


@pytest.mark.parametrize("path,line", [
    (SIGNALS, lambda u: f'{{"url": "{_escaped(u)}"}}\n'),
    (SIGNALS, lambda u: f'{{"url": "{u}"}}\n'),
    (SOURCES, lambda u: f"- url: '{u}'\n"),
    (BOARD, lambda u: f"# Acme One\n\nSee the [reference]({u}).\n"),
    (BOARD, lambda u: f"# Acme One\n\nSee <{u}>.\n"),
], ids=["json-escaped", "json", "yaml-single-quoted", "markdown-link", "markdown-autolink"])
def test_the_exact_punctuated_url_is_requested_and_its_404_fails(tmp_path, server, capsys, path, line):
    repo = make_repo(tmp_path, {}, {path: line(server.url("/important!"))})
    assert run(repo) == 1
    assert server.hit("/important!") == ["HEAD", "GET", "GET"]
    assert server.hit("/important") == []
    assert server.url("/important!") in capsys.readouterr().out


def test_an_escaped_json_url_is_decoded_to_the_path_it_names(tmp_path, server, capsys):
    url = server.url("/escaped/gone")
    repo = make_repo(tmp_path, {}, {SIGNALS: f'{{"url": "{_escaped(url)}"}}\n'})
    assert run(repo) == 1
    assert server.hit("/escaped/gone") == ["HEAD", "GET", "GET"]
    assert all("\\" not in p for _, p in server.hits)
    assert f"Dead link (HTTP 404, then 404, confirmed): {url}" in capsys.readouterr().out


def test_a_bare_url_in_prose_drops_the_sentence_punctuation(tmp_path, server):
    url = server.url("/important!")
    repo = make_repo(tmp_path, {}, {BOARD: f"# Acme One\n\nRead {url}\n"})
    assert run(repo) == 0
    assert server.hit("/important") == ["HEAD"]
    assert server.hit("/important!") == []


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


def test_check_all_dedupes_and_respects_the_concurrency_cap(monkeypatch):
    lock, state, asked = threading.Lock(), {"now": 0, "peak": 0}, []

    def fake_check(url, **_):
        with lock:
            asked.append(url)
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.05)
        with lock:
            state["now"] -= 1
        return nlc.ALIVE, "HTTP 200"

    monkeypatch.setattr(nlc, "check_url", fake_check)
    urls = [f"https://a.example/{i}" for i in range(8)] * 2
    results = nlc.check_all(urls, concurrency=3)
    assert sorted(asked) == sorted(set(urls))
    assert set(results) == set(urls)
    assert state["peak"] == 3


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
new file mode 100644
Binary files /dev/null and b/data/boards/a/b/photo.png differ
diff --git a/data/boards/a/b/notes.txt b/data/boards/a/b/notes.txt
--- /dev/null
+++ b/data/boards/a/b/notes.txt
@@ -0,0 +1,2 @@
+https://txt.example/
\\ No newline at end of file
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
    ("[guide](https://a.example/docs/user's-guide.md)", ["https://a.example/docs/user's-guide.md"]),
    ("  - 'https://a.example/it''s'", ["https://a.example/it's"]),
    ("https://github.com/o/my\\_repo", ["https://github.com/o/my_repo"]),
    ('"see https://a.example/x" and \'https://b.example/y\'', ["https://a.example/x", "https://b.example/y"]),
    # structured escapes are decoded before discovery
    ('"url": "https:\\/\\/example.com\\/gone"', ["https://example.com/gone"]),
    ('"url": "https://example.com/\\u0067one"', ["https://example.com/gone"]),
    ('"url": "https://github.com/o/my\\_repo"', ["https://github.com/o/my_repo"]),
    # punctuation inside explicit delimiters is part of the URL
    ('"url": "https://example.com/important!"', ["https://example.com/important!"]),
    ("  url: 'https://example.com/important!'", ["https://example.com/important!"]),
    ("[reference](https://example.com/important!)", ["https://example.com/important!"]),
    ("![pinout](https://example.com/pin.png) and [ref](https://example.com/a?b=c \"Title\")",
     ["https://example.com/pin.png", "https://example.com/a?b=c"]),
    ("[esc](https://example.com/a\\(b\\))", ["https://example.com/a(b)"]),
    ("<https://example.com/important!>", ["https://example.com/important!"]),
    ('"vendor_url": "https://example.com/v1."', ["https://example.com/v1."]),
    ("- 'https://example.com/v1.'", ["https://example.com/v1."]),
    # bare URLs in prose -- including prose inside a quoted string -- lose sentence punctuation
    ("See https://example.com/important!", ["https://example.com/important"]),
    ('"notes": "pinout at https://example.com/pinout."', ["https://example.com/pinout"]),
    ("unclosed [x](https://example.com/a.", ["https://example.com/a"]),
    ("a scheme alone https:// or 'https://' or \"https:\" is no URL", []),
    ("See <https:example.com>. or <https:\\/\\/example.com/x>", ["https://example.com/x"]),
    ('"url": "https://github.com/o/my\\_repo/\\u0067"', ["https://github.com/o/my_repo/g"]),
])
def test_urls_in_a_line(line, urls):
    assert nlc.urls_in(line) == urls


def test_extract_urls_dedupes_ignoring_the_fragment_and_keeps_every_location():
    found = nlc.extract_urls([
        ("a.md", 1, "url: https://a.example/p#L1"),
        ("b.md", 7, "url: https://a.example/p#L2"),
    ])
    assert found == {"https://a.example/p": [("a.md", 1), ("b.md", 7)]}


# --- the process exit code CI sees ---------------------------------------------------------
# The required schema check runs this script as a plain step: its exit code IS the verdict.

SCRIPT = Path(__file__).resolve().parent / "new_link_check.py"


@pytest.mark.parametrize("path,expected", [
    ("/ok", 0), ("/down503", 0), ("/slow", 0), ("/gone404", 1), ("/gone410", 1),
], ids=["alive", "inconclusive-5xx", "inconclusive-timeout", "dead-404", "dead-410"])
def test_the_script_exit_code_is_nonzero_only_for_a_confirmed_dead_link(tmp_path, server, path, expected):
    repo = make_repo(tmp_path, {BOARD: board_md(server.url("/ok"))},
                     {BOARD: board_md(server.url("/ok"), server.url(path))})
    proc = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), "--base", "main",
                           "--timeout", "0.5", "--recheck-delay", "0"], capture_output=True, text=True)
    assert proc.returncode == expected, proc.stdout + proc.stderr
