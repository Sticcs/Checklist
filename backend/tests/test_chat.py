from fastapi.testclient import TestClient

from app import crud
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


def test_owner_and_collaborator_can_send_and_read_messages(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    other, other_username = _join(client, task["id"])

    r = client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})
    assert r.status_code == 201
    assert r.json()["username"] == owner
    assert r.json()["text"] == "hi"

    body = other.get(f"/api/tasks/{task['id']}/messages").json()
    assert [m["text"] for m in body["messages"]] == ["hi"]
    assert body["unread_count"] == 1  # other hasn't read it yet


def test_sending_your_own_message_does_not_count_as_your_own_unread(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})

    assert client.get(f"/api/tasks/{task['id']}/messages").json()["unread_count"] == 0


def test_marking_read_clears_unread_count(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])

    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})
    assert other.get(f"/api/tasks/{task['id']}/messages").json()["unread_count"] == 1

    r = other.post(f"/api/tasks/{task['id']}/messages/read")
    assert r.status_code == 204
    assert other.get(f"/api/tasks/{task['id']}/messages").json()["unread_count"] == 0


def test_new_message_after_read_is_unread_again(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])

    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "first"})
    other.post(f"/api/tasks/{task['id']}/messages/read")
    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "second"})

    assert other.get(f"/api/tasks/{task['id']}/messages").json()["unread_count"] == 1


def test_stranger_cannot_read_or_send(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _second_guest(client)

    assert other.get(f"/api/tasks/{task['id']}/messages").status_code == 404
    assert other.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"}).status_code == 404


def test_empty_message_rejected(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    r = client.post(f"/api/tasks/{task['id']}/messages", json={"text": "   "})
    assert r.status_code == 400


def test_overlong_message_rejected(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    r = client.post(f"/api/tasks/{task['id']}/messages", json={"text": "x" * 2001})
    assert r.status_code == 400


def test_deleting_the_task_removes_messages(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})

    client.delete(f"/api/tasks/{task['id']}")

    assert crud.list_chat_messages(task["id"]) == []


def test_clearing_completed_removes_messages_for_cleared_tasks(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})

    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    client.post("/api/tasks/clear-completed")

    assert crud.list_chat_messages(task["id"]) == []


# ----------------------------- Chat summary (main-screen launcher) -----------------------------

def test_summary_lists_owned_and_shared_assignments(guest_client):
    client, owner = guest_client
    solo = _add_task(client, text="My own assignment")
    shared = _add_task(client, text="Assignment shared with a collaborator")
    other, other_username = _join(client, shared["id"])

    # The owner sees both of their own assignments (as owner), shared or not.
    body = client.get("/api/chat/summary").json()
    by_id = {a["task_id"]: a for a in body["assignments"]}
    assert by_id[solo["id"]]["is_owner"] is True
    assert by_id[shared["id"]]["is_owner"] is True

    # The collaborator only sees the one assignment they were actually
    # invited to, marked as not-owned - never the owner's other, unrelated
    # assignment.
    other_body = other.get("/api/chat/summary").json()
    other_by_id = {a["task_id"]: a for a in other_body["assignments"]}
    assert other_by_id[shared["id"]]["is_owner"] is False
    assert solo["id"] not in other_by_id


def test_summary_omits_non_assessment_tasks(guest_client):
    client, _ = guest_client
    client.post("/api/tasks", json={"text": "Plain task", "priority": "Medium", "category": "General"})

    body = client.get("/api/chat/summary").json()
    assert body["assignments"] == []


def test_summary_reflects_unread_count(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])

    other.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})

    body = client.get("/api/chat/summary").json()
    entry = next(a for a in body["assignments"] if a["task_id"] == task["id"])
    assert entry["unread_count"] == 1

    client.post(f"/api/tasks/{task['id']}/messages/read")
    body = client.get("/api/chat/summary").json()
    entry = next(a for a in body["assignments"] if a["task_id"] == task["id"])
    assert entry["unread_count"] == 0


def test_mark_read_is_safe_to_call_twice_in_quick_succession(guest_client):
    # Reproduces a real crash: React StrictMode double-invokes ChatPanel's
    # mount effect (see ChatPanel.tsx), firing mark-read twice back to back
    # - the old check-then-insert dedup let both calls see "no row yet" and
    # both insert, leaving two rows for the same (task_id, username) and
    # crashing the next unread_chat_count read with MultipleResultsFound.
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})

    r1 = client.post(f"/api/tasks/{task['id']}/messages/read")
    r2 = client.post(f"/api/tasks/{task['id']}/messages/read")
    assert r1.status_code == 204
    assert r2.status_code == 204

    r = client.get(f"/api/tasks/{task['id']}/messages")
    assert r.status_code == 200
    assert r.json()["unread_count"] == 0


def test_unread_count_survives_a_pre_existing_duplicate_read_row(guest_client):
    # Directly simulates the race's end state (two rows already present,
    # for the exact same viewer whose unread count gets read back below)
    # rather than relying on timing - confirms unread_chat_count's MAX(...)
    # aggregate can't crash on it, whichever code path produced it.
    client, username = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])
    other.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})

    from sqlalchemy import text as sql_text

    from app import db

    engine = db.get_engine()
    with engine.begin() as conn:
        for last_read in (0, 1):
            conn.execute(
                sql_text(
                    "INSERT INTO assignment_message_reads (task_id, username, last_read_message_id) "
                    "VALUES (:task_id, :username, :last_read)"
                ),
                {"task_id": task["id"], "username": username, "last_read": last_read},
            )

    r = client.get(f"/api/tasks/{task['id']}/messages")
    assert r.status_code == 200
    # Takes the more-progressed of the two duplicate rows (last_read=1), so
    # only messages after that count as unread - not a crash, not the more
    # conservative last_read=0 reading either.
    assert r.json()["unread_count"] == 0
