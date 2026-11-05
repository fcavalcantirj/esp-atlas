"""Metadata stays visible; installation paths refuse a known-broken pairing."""
from esp_atlas_core import flash

BROKEN_RECIPE = "esp32-c5-devkitc-1__esp32marauder"


def forbid_upstream_client(*args, **kwargs):
    raise AssertionError("a broken recipe must never open an upstream binary connection")


def test_broken_manifest_and_binary_are_refused_without_upstream_io(client, monkeypatch):
    monkeypatch.setattr("esp_atlas_api.main.httpx.AsyncClient", forbid_upstream_client)
    assert client.get(f"/manifest/{BROKEN_RECIPE}.json").status_code == 404
    assert client.get("/flash-bin", params={"recipe": BROKEN_RECIPE}).status_code == 403
    assert client.get("/flash-bin", params={"recipe": BROKEN_RECIPE, "part": 0}).status_code == 403
    recipes = client.get("/recipes", params={"board": "esp32-c5-devkitc-1"})
    record = next(r for r in recipes.json()["results"] if r["id"] == BROKEN_RECIPE)
    assert record["status"] == "broken"
    assert record["notes"] and record["sources"] and record["flash"]["bin_url"]


def test_old_manifest_cannot_proxy_a_recipe_now_marked_broken(client, monkeypatch):
    record = flash.get_recipe("m5cardputer__launcher")
    manifest = client.get(f"/manifest/{record['id']}.json")
    assert manifest.status_code == 200
    old_binary_url = manifest.json()["builds"][0]["parts"][0]["path"]
    monkeypatch.setattr(flash, "get_recipe", lambda _id: {**record, "status": "broken"})
    monkeypatch.setattr("esp_atlas_api.main.httpx.AsyncClient", forbid_upstream_client)
    assert client.get(old_binary_url).status_code == 403
    assert client.get(f"/manifest/{record['id']}.json").status_code == 404
