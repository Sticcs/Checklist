def test_signup_then_login(client):
    r = client.post("/api/auth/signup", json={"username": "alice", "password": "pw12345"})
    assert r.status_code == 201

    r = client.post("/api/auth/login", json={"username": "alice", "password": "pw12345"})
    assert r.status_code == 200
    assert r.json() == {"username": "alice", "is_guest": False}
    assert "session" in r.cookies


def test_login_remembers_by_default(client):
    client.post("/api/auth/signup", json={"username": "remembered", "password": "pw12345"})
    r = client.post("/api/auth/login", json={"username": "remembered", "password": "pw12345"})
    # No max_age/expires in the request body at all - "keep me logged in" is
    # opt-out, not opt-in, so an old client that's never heard of the field
    # keeps getting today's actual default (a persistent cookie).
    assert "max-age" in r.headers["set-cookie"].lower()


def test_login_with_remember_me_false_is_a_session_cookie(client):
    client.post("/api/auth/signup", json={"username": "notremembered", "password": "pw12345"})
    r = client.post(
        "/api/auth/login",
        json={"username": "notremembered", "password": "pw12345", "remember_me": False},
    )
    # No Max-Age/Expires attribute at all - the browser drops it once it's
    # actually closed, rather than it persisting for 30 days regardless.
    assert "max-age" not in r.headers["set-cookie"].lower()


def test_login_with_remember_me_true_is_explicit(client):
    client.post("/api/auth/signup", json={"username": "explicit", "password": "pw12345"})
    r = client.post(
        "/api/auth/login",
        json={"username": "explicit", "password": "pw12345", "remember_me": True},
    )
    assert "max-age" in r.headers["set-cookie"].lower()


def test_signup_duplicate_username_rejected(client):
    client.post("/api/auth/signup", json={"username": "bob", "password": "pw12345"})
    r = client.post("/api/auth/signup", json={"username": "bob", "password": "different"})
    assert r.status_code == 409


def test_login_wrong_password_rejected(client):
    client.post("/api/auth/signup", json={"username": "carol", "password": "correct"})
    r = client.post("/api/auth/login", json={"username": "carol", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user_rejected(client):
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "pw"})
    assert r.status_code == 401


def test_me_requires_auth(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_after_login(client):
    client.post("/api/auth/signup", json={"username": "dave", "password": "pw12345"})
    client.post("/api/auth/login", json={"username": "dave", "password": "pw12345"})
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json() == {"username": "dave", "is_guest": False}


def test_logout_clears_session(client):
    client.post("/api/auth/signup", json={"username": "erin", "password": "pw12345"})
    client.post("/api/auth/login", json={"username": "erin", "password": "pw12345"})
    assert client.get("/api/auth/me").status_code == 200

    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_guest_login_issues_unique_identity(client):
    r = client.post("/api/auth/guest")
    assert r.status_code == 200
    body = r.json()
    assert body["is_guest"] is True
    assert body["username"].startswith("guest_")


def test_two_guest_sessions_are_isolated(client):
    # This is the exact bug fixed in the Streamlit version this session: two
    # separate "Continue as Guest" logins used to share one literal "guest"
    # username and could see each other's tasks. Must not regress.
    from fastapi.testclient import TestClient

    from app.main import app

    client_a = client
    r_a = client_a.post("/api/auth/guest")
    username_a = r_a.json()["username"]
    client_a.post("/api/tasks", json={"text": "Guest A's secret", "priority": "Medium", "category": "General"})

    # A second, independent TestClient (separate cookie jar) simulates a fully
    # separate browser session hitting the same running app.
    client_b = TestClient(app)
    r_b = client_b.post("/api/auth/guest")
    username_b = r_b.json()["username"]

    assert username_a != username_b

    tasks_b = client_b.get("/api/tasks").json()["tasks"]
    assert all(t["text"] != "Guest A's secret" for t in tasks_b)
