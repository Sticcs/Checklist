from fastapi.testclient import TestClient

from app.main import app


def _second_guest(client):
    """A second, independent logged-in identity sharing the same test
    database as `client` but with its own cookie jar."""
    other = TestClient(app)
    r = other.post("/api/auth/guest")
    assert r.status_code == 200
    return other, r.json()["username"]


def _shopping(lists):
    return next(l for l in lists if l["kind"] == "shopping")


def test_shopping_list_get_or_create_is_idempotent(guest_client):
    client, _ = guest_client
    r1 = client.get("/api/lists")
    assert r1.status_code == 200
    shopping1 = _shopping(r1.json()["lists"])
    assert shopping1["name"] == "Shopping"

    r2 = client.get("/api/lists")
    shopping2 = _shopping(r2.json()["lists"])
    assert shopping1["id"] == shopping2["id"]


def test_create_list_defaults_to_list_1_then_list_2(guest_client):
    client, _ = guest_client
    first = client.post("/api/lists")
    assert first.status_code == 201
    assert first.json()["name"] == "List 1"
    assert first.json()["kind"] == "custom"

    second = client.post("/api/lists")
    assert second.json()["name"] == "List 2"

    r = client.get("/api/lists")
    names = [l["name"] for l in r.json()["lists"]]
    assert names == ["Shopping", "List 1", "List 2"]


def test_deleted_custom_list_name_can_be_reused(guest_client):
    client, _ = guest_client
    first = client.post("/api/lists").json()
    client.delete(f"/api/lists/{first['id']}")
    second = client.post("/api/lists").json()
    assert second["name"] == "List 1"


def test_rename_list(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists").json()
    r = client.patch(f"/api/lists/{created['id']}", json={"name": "Groceries"})
    assert r.status_code == 200
    assert r.json()["name"] == "Groceries"

    shopping = _shopping(client.get("/api/lists").json()["lists"])
    r = client.patch(f"/api/lists/{shopping['id']}", json={"name": "Weekly shop"})
    assert r.status_code == 200
    assert r.json()["name"] == "Weekly shop"


def test_rename_requires_ownership(client):
    client.post("/api/auth/guest")
    created = client.post("/api/lists").json()
    other, _ = _second_guest(client)
    r = other.patch(f"/api/lists/{created['id']}", json={"name": "Hijacked"})
    assert r.status_code == 404


def test_custom_list_delete_removes_row_and_tasks(guest_client):
    client, _ = guest_client
    # Lazily create the Shopping row first (as GET /api/lists would on a
    # real first page load) so it doesn't land on the same numeric id the
    # deleted custom list below frees up - SQLite reuses a table's highest
    # freed rowid on the very next insert when it's the only row, same as
    # every other table in this schema (see get_or_create_shopping_list's
    # docstring / the shared no-AUTOINCREMENT-keyword convention).
    client.get("/api/lists")
    created = client.post("/api/lists").json()
    task = client.post(
        "/api/tasks", json={"text": "Buy milk", "priority": "Medium", "category": "General", "list_id": created["id"]}
    )
    assert task.status_code == 201

    r = client.delete(f"/api/lists/{created['id']}")
    assert r.status_code == 204

    lists = client.get("/api/lists").json()["lists"]
    assert created["id"] not in [l["id"] for l in lists if l["kind"] == "custom"]

    tasks = client.get("/api/tasks").json()["tasks"]
    assert task.json()["id"] not in [t["id"] for t in tasks]


def test_shopping_delete_clears_items_but_keeps_the_list(guest_client):
    client, _ = guest_client
    client.post("/api/tasks", json={"text": "Milk", "priority": "Medium", "category": "Shopping"})
    client.post("/api/tasks", json={"text": "Eggs", "priority": "Medium", "category": "Shopping"})
    shopping = _shopping(client.get("/api/lists").json()["lists"])

    r = client.delete(f"/api/lists/{shopping['id']}")
    assert r.status_code == 204

    # The tab survives...
    lists = client.get("/api/lists").json()["lists"]
    shopping_after = _shopping(lists)
    assert shopping_after["id"] == shopping["id"]

    # ...but its items are gone.
    tasks = client.get("/api/tasks").json()["tasks"]
    assert [t for t in tasks if t["category"] == "Shopping"] == []


def test_list_id_survives_undo_redo(guest_client):
    """Regression test: crud.restore_state's hand-written INSERT column list
    must include list_id, or any undo/redo on any task silently resets every
    custom-list item's list_id to NULL."""
    client, _ = guest_client
    created = client.post("/api/lists").json()
    item = client.post(
        "/api/tasks",
        json={"text": "Milk", "priority": "Medium", "category": "General", "list_id": created["id"]},
    ).json()

    # An unrelated task mutation elsewhere in the account.
    other_task = client.post(
        "/api/tasks", json={"text": "Unrelated", "priority": "Medium", "category": "General"}
    ).json()
    client.patch(f"/api/tasks/{other_task['id']}/done", json={"done": True})

    client.post("/api/undo")

    tasks = client.get("/api/tasks").json()["tasks"]
    restored = next(t for t in tasks if t["id"] == item["id"])
    assert restored["list_id"] == created["id"]


def test_create_task_rejects_a_list_id_you_dont_own(client):
    client.post("/api/auth/guest")
    created = client.post("/api/lists").json()
    other, _ = _second_guest(client)
    r = other.post(
        "/api/tasks", json={"text": "x", "priority": "Medium", "category": "General", "list_id": created["id"]}
    )
    assert r.status_code == 404


def test_create_task_rejects_the_shopping_list_id(guest_client):
    """list_id is only for 'custom' lists - Shopping items are still routed
    by category alone."""
    client, _ = guest_client
    shopping = _shopping(client.get("/api/lists").json()["lists"])
    r = client.post(
        "/api/tasks", json={"text": "x", "priority": "Medium", "category": "General", "list_id": shopping["id"]}
    )
    assert r.status_code == 404


def test_list_items_do_not_appear_via_shared_with_me_or_other_users(client):
    client.post("/api/auth/guest")
    created = client.post("/api/lists").json()
    client.post(
        "/api/tasks", json={"text": "Milk", "priority": "Medium", "category": "General", "list_id": created["id"]}
    )
    other, _ = _second_guest(client)
    assert other.get("/api/lists").json()["lists"] == [_shopping(other.get("/api/lists").json()["lists"])]
    assert other.get("/api/tasks").json()["tasks"] == []


def test_list_share_link_requires_desktop_disabled(guest_client, monkeypatch):
    monkeypatch.setattr("app.routers.lists.is_desktop_build", lambda: True)
    client, _ = guest_client
    created = client.post("/api/lists").json()
    r = client.post(f"/api/lists/{created['id']}/share-link")
    assert r.status_code == 503
