"""Runtime measurements must never become catalog/admission edits."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from esp_atlas_api.runtime_popularity import SnapshotReader, resolve_records, validate_snapshot

NOW = datetime(2026, 11, 7, 19, tzinfo=timezone.utc)
DATE = "2026-11-07T19:00:00Z"


def snapshot(**changes):
    row = dict(repository_url="https://github.com/example/tool", github_repo_id=42,
               stars=0, forks=2, github_as_of=DATE)
    return dict(schema_version=1, version="run-1", catalog_revision="a"*40,
                published_at=DATE, records={"tool": {**row, **changes}})


def catalog():
    return [dict(id="tool", name="Tool", url="https://github.com/example/tool",
                 popularity=dict(stars=100, forks=20, github_repo_id=42, as_of="2026-10-01",
                                 downloads=2000), sources=[])]


def test_zero_decrease_source_and_time_without_catalog_mutation():
    records = catalog(); before = deepcopy(records)
    result = resolve_records(records, snapshot(), now=NOW)
    pop = result[0]["popularity"]
    assert (pop["stars"], pop["forks"], pop["downloads"]) == (0, 2, 2000)
    assert pop["github_as_of"] == DATE and pop["as_of"] == "2026-10-01"
    assert pop["origin"] == "runtime" and pop["snapshot_version"] == "run-1"
    assert not pop["stale"]
    assert records == before
    assert {s["field"] for s in result[0]["sources"]} >= {"popularity.stars", "popularity.forks"}


@pytest.mark.parametrize("changes", [dict(repository_url="https://github.com/other/tool"),
                                      dict(github_repo_id=77)])
def test_conflicting_binding_uses_dated_catalog_fallback(changes):
    pop = resolve_records(catalog(), snapshot(**changes), now=NOW)[0]["popularity"]
    assert pop["stars"] == 100 and pop["origin"] == "catalog" and pop["stale"]


def test_failed_snapshot_keeps_fallback_date_and_removed_records_are_not_added():
    records = resolve_records(catalog(), None, now=NOW)
    assert records[0]["popularity"]["as_of"] == "2026-10-01"
    assert resolve_records([], snapshot(), now=NOW) == []


@pytest.mark.parametrize("changes", [dict(stars=True), dict(forks=-1), dict(github_repo_id=0),
                                      dict(github_as_of="tomorrow"), dict(github_as_of="2030-01-01T00:00:00Z"),
                                      dict(repository_url="https://github.com/example/tool?x=1")])
def test_bad_snapshot_is_rejected(changes):
    with pytest.raises(ValueError):
        validate_snapshot(snapshot(**changes), now=NOW)


def test_old_runtime_observation_is_retained_but_stale():
    pop = resolve_records(catalog(), snapshot(github_as_of="2026-11-07T16:00:00Z"), now=NOW)[0]["popularity"]
    assert pop["stars"] == 0 and pop["stale"]


def test_a_newer_cited_catalog_observation_is_not_replaced_by_an_old_snapshot():
    records = catalog()
    records[0]["popularity"]["github_as_of"] = "2026-11-07T19:01:00Z"
    pop = resolve_records(records, snapshot(), now=NOW)[0]["popularity"]
    assert pop["stars"] == 100 and pop["origin"] == "catalog"


def test_missing_catalog_id_can_use_the_exact_approved_url_but_other_firmware_cannot():
    records = catalog()
    del records[0]["popularity"]["github_repo_id"]
    assert resolve_records(records, snapshot(), now=NOW)[0]["popularity"]["github_repo_id"] == 42
    records[0]["id"] = "replacement"
    assert resolve_records(records, snapshot(), now=NOW)[0]["popularity"]["stars"] == 100


def test_git_json_read_is_an_unauthenticated_get_and_never_follows_redirects(monkeypatch):
    import httpx
    from esp_atlas_api import runtime_popularity as runtime
    real_client = httpx.Client
    calls = []
    def handle(request):
        calls.append(request)
        assert request.method == "GET" and not request.content
        assert str(request.url) == runtime.DEFAULT_SNAPSHOT_URL
        assert "authorization" not in request.headers
        return httpx.Response(200, json=snapshot())
    monkeypatch.setenv("POPULARITY_RUNTIME_ENABLED", "1")
    monkeypatch.delenv("POPULARITY_SNAPSHOT_URL", raising=False)
    def client(**kwargs):
        assert kwargs["follow_redirects"] is False and kwargs["timeout"] == 2.0
        return real_client(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr(runtime.httpx, "Client", client)
    assert SnapshotReader(now=lambda: NOW).read()["version"] == "run-1"
    assert len(calls) == 1


@pytest.mark.parametrize("url", ["http://example.test/popularity.json", "https://user:secret@example.test/counts.json",
                                  "file:///tmp/popularity.json", "https://example.test/counts.json#fragment"])
def test_invalid_snapshot_location_is_rejected_before_request(monkeypatch, url):
    from esp_atlas_api import runtime_popularity as runtime
    monkeypatch.setenv("POPULARITY_SNAPSHOT_URL", url)
    monkeypatch.setattr(runtime.httpx, "Client", lambda **kw: pytest.fail("unexpected request"))
    with pytest.raises(ValueError):
        runtime._load()


@pytest.mark.parametrize("status,body", [(404,b"missing"), (429,b"limited"), (500,b"unavailable"),
                                         (302,b"redirect"), (200,b"not json"), (200,b"x"*2_000_001)])
def test_failed_git_json_fetch_retains_last_valid_snapshot(monkeypatch, status, body):
    import httpx
    from esp_atlas_api import runtime_popularity as runtime
    real_client = httpx.Client
    replies = iter([httpx.Response(200,json=snapshot()), httpx.Response(status,content=body)])
    def handle(request):
        return next(replies)
    monkeypatch.setattr(runtime.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    monkeypatch.setenv("POPULARITY_RUNTIME_ENABLED", "1")
    clock = [0]
    reader = SnapshotReader(clock=lambda: clock[0], now=lambda: NOW)
    assert reader.read()["version"] == "run-1"
    clock[0] = 31
    assert reader.read()["version"] == "run-1"


def test_corrupt_and_older_store_publications_keep_last_good(monkeypatch):
    monkeypatch.setenv("POPULARITY_RUNTIME_ENABLED", "1")
    older = snapshot(github_as_of="2026-11-07T18:00:00Z")
    older["published_at"] = "2026-11-07T18:00:00Z"
    replies = iter([snapshot(), {"schema_version": 2}, older])
    clock = [0]
    reader = SnapshotReader(load=lambda: next(replies), clock=lambda: clock[0], now=lambda: NOW)
    for tick in [0, 31, 62]:
        clock[0] = tick
        assert reader.read()["published_at"] == DATE


def test_reader_cache_failure_and_disabled_mode(monkeypatch):
    clock = [0]; calls = []
    def load():
        calls.append(1)
        if len(calls) > 1: raise OSError("store unavailable")
        return snapshot()
    reader = SnapshotReader(load=load, clock=lambda: clock[0], now=lambda: NOW)
    assert reader.read() is None and not calls
    monkeypatch.setenv("POPULARITY_RUNTIME_ENABLED", "1")
    assert reader.read()["version"] == "run-1"
    assert reader.read()["version"] == "run-1" and len(calls) == 1
    clock[0] = 31
    assert reader.read()["published_at"] == DATE and len(calls) == 2
    reader.read()["records"].clear()
    assert reader.read()["records"]  # callers cannot poison the cached snapshot
    monkeypatch.setenv("POPULARITY_RUNTIME_ENABLED", "0")
    assert reader.read() is None


def test_examples_and_list_sort_use_the_same_runtime_values(client, monkeypatch):
    import esp_atlas_api.main as main
    records = [dict(**catalog()[0], type="firmware", category="multi", socs=[]),
               dict(id="other", name="Other", url="https://github.com/example/other",
                    type="firmware", category="multi", socs=[], sources=[], popularity={"stars":50,"forks":0})]
    monkeypatch.setenv("POPULARITY_RUNTIME_ENABLED", "1")
    monkeypatch.setattr(main, "core_list_firmware", lambda: records)
    monkeypatch.setattr(main, "core_get_firmware", lambda fid: next(r for r in records if r["id"] == fid))
    monkeypatch.setattr(main, "core_read_examples", lambda **kw: [
        {"id":"run-tool","label":"Run Tool","kind":"firmware","group":"run-firmware","firmware":"tool","count":1,"stars":100},
        {"id":"run-other","label":"Run Other","kind":"firmware","group":"run-firmware","firmware":"other","count":1,"stars":50}])
    client.app.state.popularity_reader = SnapshotReader(load=snapshot, now=lambda: NOW)
    listing = client.get("/firmware").json()["results"]
    examples = client.get("/examples").json()["results"]
    detail = client.get("/firmware/tool").json()
    assert [r["id"] for r in listing] == ["other","tool"]
    assert [r["firmware"] for r in examples] == ["other","tool"]
    assert detail["popularity"]["stars"] == examples[1]["stars"] == 0
    assert detail["popularity"]["snapshot_version"] == examples[1]["snapshot_version"] == "run-1"
