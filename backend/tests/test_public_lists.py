from fastapi.testclient import TestClient

from app.main import app


def _fresh_anonymous_client():
    """A brand-new client with no cookies at all - never calls any
    /api/auth/* endpoint - simulating a visitor who followed a public link
    with zero login."""
    return TestClient(app)


def _shopping(lists):
    return next(l for l in lists if l["kind"] == "shopping")


def test_public_get_works_with_zero_cookies(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists").json()
    client.post(
        "/api/tasks", json={"text": "Milk", "priority": "Medium", "category": "General", "list_id": created["id"]}
    )
    token = client.post(f"/api/lists/{created['id']}/share-link").json()["token"]

    anon = _fresh_anonymous_client()
    r = anon.get(f"/api/public/lists/{token}")
    assert r.status_code == 200
    body = r.json()
    assert body["list_name"] == created["name"]
    assert [i["text"] for i in body["items"]] == ["Milk"]
    assert body["items"][0]["done"] is False
    # No owner/account metadata leaked.
    assert "username" not in body
    assert "owner" not in body


def test_public_patch_toggles_without_auth(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists").json()
    item = client.post(
        "/api/tasks", json={"text": "Milk", "priority": "Medium", "category": "General", "list_id": created["id"]}
    ).json()
    token = client.post(f"/api/lists/{created['id']}/share-link").json()["token"]

    anon = _fresh_anonymous_client()
    r = anon.patch(f"/api/public/lists/{token}/items/{item['id']}", json={"done": True})
    assert r.status_code == 200
    assert r.json()["items"][0]["done"] is True

    # Reflected back to the owner's own view.
    tasks = client.get("/api/tasks").json()["tasks"]
    assert next(t for t in tasks if t["id"] == item["id"])["done"] is True


def test_public_shopping_link_works(guest_client):
    client, _ = guest_client
    client.post("/api/tasks", json={"text": "Milk", "priority": "Medium", "category": "Shopping"})
    shopping = _shopping(client.get("/api/lists").json()["lists"])
    token = client.post(f"/api/lists/{shopping['id']}/share-link").json()["token"]

    anon = _fresh_anonymous_client()
    r = anon.get(f"/api/public/lists/{token}")
    assert r.status_code == 200
    assert [i["text"] for i in r.json()["items"]] == ["Milk"]


def test_invalid_token_404s(client):
    r = client.get("/api/public/lists/not-a-real-token")
    assert r.status_code == 404


def test_revoked_token_404s(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists").json()
    token = client.post(f"/api/lists/{created['id']}/share-link").json()["token"]
    client.delete(f"/api/lists/{created['id']}/share-link")

    anon = _fresh_anonymous_client()
    assert anon.get(f"/api/public/lists/{token}").status_code == 404


def test_idor_custom_list_cannot_toggle_item_from_another_list(guest_client):
    client, _ = guest_client
    list_a = client.post("/api/lists").json()
    list_b = client.post("/api/lists").json()
    item_b = client.post(
        "/api/tasks", json={"text": "In B", "priority": "Medium", "category": "General", "list_id": list_b["id"]}
    ).json()
    token_a = client.post(f"/api/lists/{list_a['id']}/share-link").json()["token"]

    anon = _fresh_anonymous_client()
    r = anon.patch(f"/api/public/lists/{token_a}/items/{item_b['id']}", json={"done": True})
    # No error leaked - just a no-op that doesn't touch the item.
    assert r.status_code == 200

    tasks = client.get("/api/tasks").json()["tasks"]
    assert next(t for t in tasks if t["id"] == item_b["id"])["done"] is False


def test_idor_shopping_list_cannot_toggle_another_accounts_item(client):
    client.post("/api/auth/guest")
    other = TestClient(app)
    other_username = other.post("/api/auth/guest").json()["username"]
    assert other_username

    other.post("/api/tasks", json={"text": "Other's milk", "priority": "Medium", "category": "Shopping"})
    other_shopping = _shopping(other.get("/api/lists").json()["lists"])
    other_item = next(
        t for t in other.get("/api/tasks").json()["tasks"] if t["text"] == "Other's milk"
    )

    client.post("/api/tasks", json={"text": "My milk", "priority": "Medium", "category": "Shopping"})
    my_shopping = _shopping(client.get("/api/lists").json()["lists"])
    my_token = client.post(f"/api/lists/{my_shopping['id']}/share-link").json()["token"]

    anon = _fresh_anonymous_client()
    r = anon.patch(f"/api/public/lists/{my_token}/items/{other_item['id']}", json={"done": True})
    assert r.status_code == 200

    other_tasks = other.get("/api/tasks").json()["tasks"]
    assert next(t for t in other_tasks if t["id"] == other_item["id"])["done"] is False
