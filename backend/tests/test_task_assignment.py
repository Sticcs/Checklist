def _add_task(client, text="Buy milk", priority="High", category="House", due_date=None):
    r = client.post(
        "/api/tasks",
        json={"text": text, "priority": priority, "category": category, "due_date": due_date},
    )
    assert r.status_code == 201
    return r.json()


def test_assign_files_assessment_under_a_task(guest_client):
    client, _ = guest_client
    main_task = _add_task(client, text="Study for finals", category="Study")
    assessment = _add_task(client, text="Math final", category="Assessment")

    r = client.patch(f"/api/tasks/{assessment['id']}/assign", json={"assigned_task_id": main_task["id"]})
    assert r.status_code == 200
    assert r.json()["assigned_task_id"] == main_task["id"]

    # Persisted, not just echoed back.
    tasks = {t["id"]: t for t in client.get("/api/tasks").json()["tasks"]}
    assert tasks[assessment["id"]]["assigned_task_id"] == main_task["id"]
    assert tasks[main_task["id"]]["assigned_task_id"] is None


def test_a_task_can_collect_multiple_assessments(guest_client):
    client, _ = guest_client
    main_task = _add_task(client, text="Study for finals", category="Study")
    math = _add_task(client, text="Math final", category="Assessment")
    history = _add_task(client, text="History final", category="Assessment")

    client.patch(f"/api/tasks/{math['id']}/assign", json={"assigned_task_id": main_task["id"]})
    client.patch(f"/api/tasks/{history['id']}/assign", json={"assigned_task_id": main_task["id"]})

    tasks = {t["id"]: t for t in client.get("/api/tasks").json()["tasks"]}
    assert tasks[math["id"]]["assigned_task_id"] == main_task["id"]
    assert tasks[history["id"]]["assigned_task_id"] == main_task["id"]


def test_unassign_clears_it(guest_client):
    client, _ = guest_client
    main_task = _add_task(client, category="Study")
    assessment = _add_task(client, category="Assessment")
    client.patch(f"/api/tasks/{assessment['id']}/assign", json={"assigned_task_id": main_task["id"]})

    r = client.patch(f"/api/tasks/{assessment['id']}/assign", json={"assigned_task_id": None})
    assert r.status_code == 200
    assert r.json()["assigned_task_id"] is None


def test_reassigning_overwrites_the_previous_assignment(guest_client):
    client, _ = guest_client
    task_a = _add_task(client, text="Task A", category="Study")
    task_b = _add_task(client, text="Task B", category="Work")
    assessment = _add_task(client, category="Assessment")

    client.patch(f"/api/tasks/{assessment['id']}/assign", json={"assigned_task_id": task_a["id"]})
    r = client.patch(f"/api/tasks/{assessment['id']}/assign", json={"assigned_task_id": task_b["id"]})
    assert r.json()["assigned_task_id"] == task_b["id"]


def test_assign_requires_the_assessment_to_exist(guest_client):
    client, _ = guest_client
    main_task = _add_task(client, category="Study")
    r = client.patch("/api/tasks/999999/assign", json={"assigned_task_id": main_task["id"]})
    assert r.status_code == 404


def test_assign_requires_the_target_task_to_exist(guest_client):
    client, _ = guest_client
    assessment = _add_task(client, category="Assessment")
    r = client.patch(f"/api/tasks/{assessment['id']}/assign", json={"assigned_task_id": 999999})
    assert r.status_code == 404


def test_cannot_assign_to_another_users_task(client):
    client.post("/api/auth/guest")
    other_task = _add_task(client, category="Study")
    client.post("/api/auth/logout")
    client.post("/api/auth/guest")  # a second, different guest account
    assessment = _add_task(client, category="Assessment")

    r = client.patch(f"/api/tasks/{assessment['id']}/assign", json={"assigned_task_id": other_task["id"]})
    assert r.status_code == 404


def test_deleting_the_assigned_task_clears_the_assignment(guest_client):
    client, _ = guest_client
    main_task = _add_task(client, category="Study")
    assessment = _add_task(client, category="Assessment")
    client.patch(f"/api/tasks/{assessment['id']}/assign", json={"assigned_task_id": main_task["id"]})

    client.delete(f"/api/tasks/{main_task['id']}")

    tasks = client.get("/api/tasks").json()["tasks"]
    assert tasks[0]["id"] == assessment["id"]
    assert tasks[0]["assigned_task_id"] is None


def test_clearing_completed_clears_assignments_to_them(guest_client):
    client, _ = guest_client
    main_task = _add_task(client, category="Study")
    assessment = _add_task(client, category="Assessment")
    client.patch(f"/api/tasks/{assessment['id']}/assign", json={"assigned_task_id": main_task["id"]})
    client.patch(f"/api/tasks/{main_task['id']}/done", json={"done": True})

    client.post("/api/tasks/clear-completed")

    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == assessment["id"]
    assert tasks[0]["assigned_task_id"] is None


def test_assign_requires_auth(client):
    r = client.patch("/api/tasks/1/assign", json={"assigned_task_id": None})
    assert r.status_code == 401
