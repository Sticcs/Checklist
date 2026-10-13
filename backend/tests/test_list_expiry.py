from fastapi.testclient import TestClient

from app.main import app


def _second_guest(client):
    other = TestClient(app)
    r = other.post("/api/auth/guest")
    assert r.status_code == 200
    return other, r.json()["username"]


def _add_task(client, text="Task", priority="Medium", category="General", list_id=None):
    r = client.post(
        "/api/tasks",
        json={"text": text, "priority": priority, "category": category, "due_date": None, "list_id": list_id},
    )
    assert r.status_code == 201
    return r.json()


def test_create_expiry_list_requires_expires_at(guest_client):
    client, _ = guest_client
    r = client.post("/api/lists", json={"kind": "expiry"})
    assert r.status_code == 400


def test_create_expiry_list(guest_client):
    client, _ = guest_client
    r = client.post("/api/lists", json={"kind": "expiry", "expires_at": "2026-12-31T23:59"})
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "expiry"
    assert body["expires_at"] == "2026-12-31T23:59"
    assert body["created_at"]


def test_invalid_kind_rejected(guest_client):
    client, _ = guest_client
    r = client.post("/api/lists", json={"kind": "shopping"})
    assert r.status_code == 400
    r2 = client.post("/api/lists", json={"kind": "bogus"})
    assert r2.status_code == 400


def test_expiry_list_appears_in_get_lists(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists", json={"kind": "expiry", "expires_at": "2026-12-31T23:59"}).json()
    lists = client.get("/api/lists").json()["lists"]
    assert any(l["id"] == created["id"] and l["kind"] == "expiry" for l in lists)


def test_expiry_and_custom_lists_share_one_numbering_sequence(guest_client):
    client, _ = guest_client
    custom = client.post("/api/lists", json={"kind": "custom"}).json()
    expiry = client.post("/api/lists", json={"kind": "expiry", "expires_at": "2026-12-31T23:59"}).json()
    assert custom["name"] == "List 2"
    assert expiry["name"] == "List 3"


def test_set_expires_at(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists", json={"kind": "expiry", "expires_at": "2026-12-31T23:59"}).json()
    r = client.patch(f"/api/lists/{created['id']}/expires-at", json={"expires_at": "2027-01-15T12:00"})
    assert r.status_code == 200
    assert r.json()["expires_at"] == "2027-01-15T12:00"


def test_set_expires_at_404_for_someone_elses_list(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists", json={"kind": "expiry", "expires_at": "2026-12-31T23:59"}).json()
    stranger, _ = _second_guest(client)
    r = stranger.patch(f"/api/lists/{created['id']}/expires-at", json={"expires_at": "2027-01-15T12:00"})
    assert r.status_code == 404


def test_task_can_be_created_in_an_expiry_list(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists", json={"kind": "expiry", "expires_at": "2026-12-31T23:59"}).json()
    task = _add_task(client, list_id=created["id"])
    assert task["list_id"] == created["id"]


def test_task_can_be_moved_into_an_expiry_list(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists", json={"kind": "expiry", "expires_at": "2026-12-31T23:59"}).json()
    task = _add_task(client)
    r = client.patch(f"/api/tasks/{task['id']}/list", json={"list_id": created["id"]})
    assert r.status_code == 200
    assert r.json()["list_id"] == created["id"]


def test_deleting_an_expiry_list_fully_removes_it(guest_client):
    client, _ = guest_client
    # Touch Shopping/Main first (lazily created on this GET) so the expiry
    # list created below is never the lowest/only row in `lists` - without
    # this, SQLite's plain INTEGER PRIMARY KEY (no AUTOINCREMENT keyword)
    # can recycle a deleted row's id onto the *next* insert (Shopping/Main,
    # lazily created on the next GET), which would make an id-based "is it
    # really gone" check pass for the wrong reason, or fail by coincidence.
    client.get("/api/lists")
    created = client.post("/api/lists", json={"kind": "expiry", "expires_at": "2026-12-31T23:59"}).json()
    task = _add_task(client, text="Inside the expiry list", list_id=created["id"])

    r = client.delete(f"/api/lists/{created['id']}")
    assert r.status_code == 204

    lists = client.get("/api/lists").json()["lists"]
    assert not any(l["kind"] == "expiry" for l in lists)
    assert not any(l["id"] == created["id"] for l in lists)
    tasks = client.get("/api/tasks").json()["tasks"]
    assert not any(t["id"] == task["id"] for t in tasks)
