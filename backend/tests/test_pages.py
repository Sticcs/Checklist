from fastapi.testclient import TestClient

from app.main import app


def _add_task(client, text="Assignment", priority="Medium", category="Assessment", due_date=None):
    r = client.post(
        "/api/tasks",
        json={"text": text, "priority": priority, "category": category, "due_date": due_date},
    )
    assert r.status_code == 201
    return r.json()


def _second_guest(client):
    other = TestClient(app)
    r = other.post("/api/auth/guest")
    assert r.status_code == 200
    return other, r.json()["username"]


def _join(client, task_id):
    token = client.post(f"/api/tasks/{task_id}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")
    return other, other_username


def test_add_page_creates_a_new_page(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    assert task["pages"] == []

    r = client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Notes"})
    assert r.status_code == 201
    pages = r.json()["pages"]
    # The task had no pages saved yet, so the implicit "Page 1" (synthesized
    # from the legacy notes field, same as the frontend's defaultFirstPage)
    # is preserved alongside the newly added one.
    assert len(pages) == 2
    assert pages[0]["id"] == "page-1"
    assert pages[1]["title"] == "Notes"
    assert pages[1]["content"] == ""
    assert pages[1]["id"]  # server-generated, non-empty


def test_rename_page_updates_only_that_page(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Page A"})
    page_b = client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Page B"}).json()["pages"][-1]

    r = client.patch(f"/api/tasks/{task['id']}/pages/{page_b['id']}", json={"title": "Renamed B"})
    assert r.status_code == 200
    titles = {p["id"]: p["title"] for p in r.json()["pages"]}
    assert titles[page_b["id"]] == "Renamed B"
    assert "Page A" in titles.values()


def test_delete_page_removes_it(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Page A"})
    page_b = client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Page B"}).json()["pages"][-1]

    r = client.delete(f"/api/tasks/{task['id']}/pages/{page_b['id']}")
    assert r.status_code == 200
    titles = {p["title"] for p in r.json()["pages"]}
    assert titles == {"Page 1", "Page A"}


def test_delete_page_refuses_to_remove_the_last_one(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    assert task["pages"] == []

    # Nothing has been added yet, so the task is down to its one implicit
    # page ("page-1", the frontend's well-known synthesized id) - deleting
    # it must be refused rather than leaving the task with zero pages.
    r = client.delete(f"/api/tasks/{task['id']}/pages/page-1")
    assert r.status_code == 200
    assert len(r.json()["pages"]) == 1
    assert r.json()["pages"][0]["id"] == "page-1"

    # Same guard applies once there are real pages, down to the last one.
    second = client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Second"}).json()["pages"][-1]
    client.delete(f"/api/tasks/{task['id']}/pages/{second['id']}")
    r2 = client.delete(f"/api/tasks/{task['id']}/pages/page-1")
    assert len(r2.json()["pages"]) == 1


def test_add_page_is_undoable(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Notes"})
    assert len(client.get(f"/api/tasks/{task['id']}").json()["pages"]) == 2

    r = client.post("/api/undo")
    assert r.status_code == 200
    assert client.get(f"/api/tasks/{task['id']}").json()["pages"] == []


def test_delete_page_is_undoable(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Page A"})
    page_b = client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Page B"}).json()["pages"][-1]
    client.delete(f"/api/tasks/{task['id']}/pages/{page_b['id']}")
    assert len(client.get(f"/api/tasks/{task['id']}").json()["pages"]) == 2

    r = client.post("/api/undo")
    assert r.status_code == 200
    titles = {p["title"] for p in client.get(f"/api/tasks/{task['id']}").json()["pages"]}
    assert titles == {"Page 1", "Page A", "Page B"}


def test_rename_page_is_undoable(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    page = client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Original"}).json()["pages"][-1]
    client.patch(f"/api/tasks/{task['id']}/pages/{page['id']}", json={"title": "Renamed"})
    titles = {p["id"]: p["title"] for p in client.get(f"/api/tasks/{task['id']}").json()["pages"]}
    assert titles[page["id"]] == "Renamed"

    r = client.post("/api/undo")
    assert r.status_code == 200
    titles = {p["id"]: p["title"] for p in client.get(f"/api/tasks/{task['id']}").json()["pages"]}
    assert titles[page["id"]] == "Original"


def test_collaborator_can_add_delete_rename_pages(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])

    add = other.post(f"/api/tasks/{task['id']}/pages", json={"title": "From collaborator"})
    assert add.status_code == 201
    page = add.json()["pages"][-1]

    rename = other.patch(f"/api/tasks/{task['id']}/pages/{page['id']}", json={"title": "Renamed by collaborator"})
    assert rename.status_code == 200

    client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Second page"})
    delete = other.delete(f"/api/tasks/{task['id']}/pages/{page['id']}")
    assert delete.status_code == 200
    titles = {p["title"] for p in delete.json()["pages"]}
    assert titles == {"Page 1", "Second page"}


def test_stranger_cannot_touch_pages(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    page = client.post(f"/api/tasks/{task['id']}/pages", json={"title": "Page A"}).json()["pages"][0]
    stranger, _ = _second_guest(client)

    assert stranger.post(f"/api/tasks/{task['id']}/pages", json={"title": "x"}).status_code == 404
    assert stranger.patch(f"/api/tasks/{task['id']}/pages/{page['id']}", json={"title": "x"}).status_code == 404
    assert stranger.delete(f"/api/tasks/{task['id']}/pages/{page['id']}").status_code == 404
