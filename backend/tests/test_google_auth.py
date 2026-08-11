from app.config import settings


def test_google_login_not_configured_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", None)
    r = client.get("/api/auth/google/login", follow_redirects=False)
    assert r.status_code == 503


def test_google_login_redirects_to_google_with_state_cookie(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    r = client.get("/api/auth/google/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=test-client-id" in r.headers["location"]
    assert "google_oauth_state" in r.cookies


def test_google_callback_rejects_missing_state(client):
    r = client.get("/api/auth/google/callback", params={"code": "abc"}, follow_redirects=False)
    assert r.status_code == 400


def test_google_callback_rejects_mismatched_state(client):
    client.cookies.set("google_oauth_state", "expected-state")
    r = client.get(
        "/api/auth/google/callback",
        params={"code": "abc", "state": "wrong-state"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_google_callback_error_param_redirects_home(client, monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    r = client.get("/api/auth/google/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "http://testserver/?google_auth=failed"


class _FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


class _FakeHttpxClient:
    """Stands in for httpx.Client so the callback test never makes a real
    network call to Google - just returns a canned token + userinfo pair."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, data=None):
        return _FakeResponse(200, {"access_token": "fake-access-token"})

    def get(self, url, headers=None):
        return _FakeResponse(200, {"sub": "google-sub-123", "email": "newperson@example.com"})


def test_google_callback_happy_path_creates_user_and_logs_in(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeHttpxClient)

    # google_login sets the state cookie the callback checks against - a real
    # sign-in always goes through this first.
    login_resp = client.get("/api/auth/google/login", follow_redirects=False)
    state = login_resp.cookies["google_oauth_state"]

    r = client.get(
        "/api/auth/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "http://testserver/"
    assert "session" in r.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {"username": "newperson", "is_guest": False}


def test_get_or_create_google_user_returns_same_account_on_repeat_login(client):
    from app import crud

    username = crud.get_or_create_google_user("google-sub-999", "repeat@example.com")
    username_again = crud.get_or_create_google_user("google-sub-999", "repeat@example.com")
    assert username == username_again


def test_get_or_create_google_user_dedupes_username_collisions(client):
    from app import crud

    crud.create_user("shared", "somepassword")
    google_username = crud.get_or_create_google_user("google-sub-abc", "shared@example.com")
    assert google_username != "shared"
    assert google_username.startswith("shared")


def test_get_or_create_google_user_is_separate_from_manual_account_with_same_email(client):
    """Signing in with Google never merges into an existing username/password
    account, even if the email matches - see get_or_create_google_user's
    docstring for why."""
    from app import crud

    crud.create_user("alice", "manualpassword123")
    google_username = crud.get_or_create_google_user("google-sub-alice", "alice@example.com")
    assert google_username != "alice"

    # The manual account's password still works and is untouched.
    assert crud.verify_user("alice", "manualpassword123") is True
