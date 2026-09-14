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


def _main(lists):
    return next(l for l in lists if l["kind"] == "main")


def test_shopping_list_get_or_create_is_idempotent(guest_client):
    client, _ = guest_client
    r1 = client.get("/api/lists")
    assert r1.status_code == 200
    shopping1 = _shopping(r1.json()["lists"])
    assert shopping1["name"] == "Shopping"

    r2 = client.get("/api/lists")
    shopping2 = _shopping(r2.json()["lists"])
    assert shopping1["id"] == shopping2["id"]


def test_create_list_defaults_to_list_2_then_list_3(guest_client):
    # Starts at 2, not 1 - "List 1" is always taken by the account's own
    # `kind='main'` row (see create_list's docstring in crud.py).
    client, _ = guest_client
    first = client.post("/api/lists")
    assert first.status_code == 201
    assert first.json()["name"] == "List 2"
    assert first.json()["kind"] == "custom"

    second = client.post("/api/lists")
    assert second.json()["name"] == "List 3"

    r = client.get("/api/lists")
    names = [l["name"] for l in r.json()["lists"]]
    # get_lists lazily creates the main list too (its own "List 1") the
    # moment it's called - which hasn't happened yet at this point in the
    # test, since create_list itself doesn't trigger it.
    assert names == ["Shopping", "List 1", "List 2", "List 3"]


def test_deleted_custom_list_name_can_be_reused(guest_client):
    client, _ = guest_client
    first = client.post("/api/lists").json()
    client.delete(f"/api/lists/{first['id']}")
    second = client.post("/api/lists").json()
    assert second["name"] == "List 2"


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


def test_create_task_accepts_the_main_list_id(guest_client):
    """The main list ("List 1") is a real, list_id-addressable list just
    like any custom one - unlike Shopping, it's a valid create_task target."""
    client, _ = guest_client
    main = _main(client.get("/api/lists").json()["lists"])
    r = client.post(
        "/api/tasks", json={"text": "x", "priority": "Medium", "category": "General", "list_id": main["id"]}
    )
    assert r.status_code == 201
    assert r.json()["list_id"] == main["id"]


def test_list_items_do_not_appear_via_shared_with_me_or_other_users(client):
    client.post("/api/auth/guest")
    created = client.post("/api/lists").json()
    client.post(
        "/api/tasks", json={"text": "Milk", "priority": "Medium", "category": "General", "list_id": created["id"]}
    )
    other, _ = _second_guest(client)
    # A brand-new account gets its own Shopping and main list, never the
    # other user's custom one.
    other_kinds = {l["kind"] for l in other.get("/api/lists").json()["lists"]}
    assert other_kinds == {"shopping", "main"}
    assert other.get("/api/tasks").json()["tasks"] == []


def test_list_share_link_requires_desktop_disabled(guest_client, monkeypatch):
    monkeypatch.setattr("app.routers.lists.is_desktop_build", lambda: True)
    client, _ = guest_client
    created = client.post("/api/lists").json()
    r = client.post(f"/api/lists/{created['id']}/share-link")
    assert r.status_code == 503


# ----------------------------- The "main" list (List 1) -----------------------------


def test_main_list_is_auto_created_and_orphans_backfilled(guest_client):
    client, _ = guest_client
    # A plain task with no list_id - the kind of row that existed before
    # the main list was a real `lists` row at all.
    orphan = client.post(
        "/api/tasks", json={"text": "Orphan", "priority": "Medium", "category": "Personal"}
    ).json()
    assert orphan["list_id"] is None

    lists = client.get("/api/lists").json()["lists"]
    main = _main(lists)
    assert main["name"] == "List 1"
    assert main["is_simple"] is False

    tasks = client.get("/api/tasks").json()["tasks"]
    assert next(t for t in tasks if t["id"] == orphan["id"])["list_id"] == main["id"]

    # Calling it again doesn't spawn a second 'main' row.
    lists2 = client.get("/api/lists").json()["lists"]
    assert len([l for l in lists2 if l["kind"] == "main"]) == 1
    assert _main(lists2)["id"] == main["id"]


def test_existing_custom_lists_keep_their_order_after_main_list_created(guest_client):
    """A user who already created real custom lists before the main list
    existed shouldn't see them reordered behind it - get_lists assembles
    [shopping, main, *customs] as a fixed sequence, never sorting the main
    list against the customs by id."""
    client, _ = guest_client
    client.get("/api/lists")  # seed Shopping first, like a real first load
    list_a = client.post("/api/lists").json()
    list_b = client.post("/api/lists").json()

    lists = client.get("/api/lists").json()["lists"]
    names = [l["name"] for l in lists]
    assert names == ["Shopping", "List 1", list_a["name"], list_b["name"]]


def test_orphan_created_after_migration_joins_existing_main_list(guest_client):
    client, _ = guest_client
    client.get("/api/lists")  # main list now exists
    main_id = _main(client.get("/api/lists").json()["lists"])["id"]

    # Simulates a later orphan-producing event (e.g. import) after the main
    # list already exists.
    later_orphan = client.post(
        "/api/tasks", json={"text": "Later orphan", "priority": "Medium", "category": "Personal"}
    ).json()

    lists = client.get("/api/lists").json()["lists"]
    assert len([l for l in lists if l["kind"] == "main"]) == 1
    assert _main(lists)["id"] == main_id

    tasks = client.get("/api/tasks").json()["tasks"]
    assert next(t for t in tasks if t["id"] == later_orphan["id"])["list_id"] == main_id


def test_main_list_delete_clears_but_keeps_the_list(guest_client):
    """Unlike a custom list, the main list always exists exactly once per
    account (like Shopping) and gets silently re-created the moment it's
    missing - so "deleting" it clears its items instead of removing the
    row, same as Shopping, or the delete would just respawn an empty list
    a moment later on the next load."""
    client, _ = guest_client
    task = client.post(
        "/api/tasks", json={"text": "In list 1", "priority": "Medium", "category": "Personal"}
    ).json()
    main = _main(client.get("/api/lists").json()["lists"])

    r = client.delete(f"/api/lists/{main['id']}")
    assert r.status_code == 204

    lists = client.get("/api/lists").json()["lists"]
    main_after = _main(lists)
    assert main_after["id"] == main["id"]

    tasks = client.get("/api/tasks").json()["tasks"]
    assert task["id"] not in [t["id"] for t in tasks]


# ----------------------------- Rich vs. simple -----------------------------


def test_lists_default_to_rich_except_shopping(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists").json()
    assert created["is_simple"] is False

    lists = client.get("/api/lists").json()["lists"]
    assert _shopping(lists)["is_simple"] is True
    assert _main(lists)["is_simple"] is False


def test_convert_list_to_simple_and_back(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists").json()

    r = client.patch(f"/api/lists/{created['id']}/simple", json={"is_simple": True})
    assert r.status_code == 200
    assert r.json()["is_simple"] is True

    r = client.patch(f"/api/lists/{created['id']}/simple", json={"is_simple": False})
    assert r.status_code == 200
    assert r.json()["is_simple"] is False


def test_set_simple_requires_ownership(client):
    client.post("/api/auth/guest")
    created = client.post("/api/lists").json()
    other, _ = _second_guest(client)
    r = other.patch(f"/api/lists/{created['id']}/simple", json={"is_simple": True})
    assert r.status_code == 404


def test_only_simple_lists_can_be_shared(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists").json()

    r = client.post(f"/api/lists/{created['id']}/share-link")
    assert r.status_code == 400

    client.patch(f"/api/lists/{created['id']}/simple", json={"is_simple": True})
    r = client.post(f"/api/lists/{created['id']}/share-link")
    assert r.status_code == 200
