import secrets
from datetime import datetime
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from app import crud
from app.config import settings
from app.models import (
    ExportPayload,
    ImportResponse,
    LoginRequest,
    SignupRequest,
    SyncRequest,
    UserResponse,
    WebsiteLinkResponse,
)
from app.paths import is_desktop_build
from app.security import (
    CurrentUser,
    clear_session_cookie,
    get_current_user,
    make_guest_username,
    set_session_cookie,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
OAUTH_STATE_COOKIE = "google_oauth_state"


# ----------------------------- Desktop <-> website sync -----------------------------
# The desktop app's own server is otherwise fully local/offline (see
# app/paths.py) - this is the one place it deliberately reaches out to the
# real deployed site (settings.public_base_url), to either pull a website
# account's data in or push its own data up, by re-authenticating against it.
# Whichever credentials work get remembered (crud.set_website_link, keyed to
# the local account) so this local account stays "linked" across app
# restarts - Pull/Push/autosave don't need them re-entered until the user
# deliberately links a different website account, which just overwrites the
# old link.
#
# Only ever this one direction (app -> production, an ordinary outbound
# request) - there's no way to go the other way, i.e. no "pull from the app"
# button on the website itself: the app's server only exists at
# 127.0.0.1:<random-port> on the user's own machine while it happens to be
# open, which Render's servers have no route to (no fixed address, and
# almost always behind a NAT/firewall besides).


def _resolve_website_credentials(
    current_user: CurrentUser, body: SyncRequest | None
) -> tuple[str, str] | None:
    """Explicit credentials in the request (the user (re)linking, from
    WebsiteSyncButtons's form) always win and become the new link. Without
    them (the autosave timer, Ctrl+S, or the exit-save prompt - see
    AutosaveIndicator.tsx/ExitSavePrompt.tsx, which never handle the
    password at all), falls back to whatever this local account is already
    linked to. Returns None if there's nothing to fall back to."""
    if body and body.username and body.password:
        return body.username, body.password
    link = crud.get_website_link(current_user.username)
    return (link["website_username"], link["website_password"]) if link else None


def _website_session_cookie(client: httpx.Client, username: str, password: str) -> str | None:
    """Logs into the real deployed site with these credentials and returns
    its session cookie, or None if they don't match a website account."""
    login_resp = client.post(
        f"{settings.public_base_url}/api/auth/login",
        json={"username": username, "password": password},
    )
    if login_resp.status_code != 200:
        return None
    return login_resp.cookies.get(settings.cookie_name)


def _fetch_from_website(username: str, password: str) -> list | None:
    """Returns the website account's exported tasks, or None if the
    credentials don't match or the site couldn't be reached. Never raises."""
    try:
        with httpx.Client(timeout=15) as client:
            session_cookie = _website_session_cookie(client, username, password)
            if not session_cookie:
                return None
            export_resp = client.get(
                f"{settings.public_base_url}/api/export",
                cookies={settings.cookie_name: session_cookie},
            )
            if export_resp.status_code != 200:
                return None
            return export_resp.json().get("tasks", [])
    except httpx.HTTPError:
        return None


def _push_to_website(username: str, password: str, payload: dict) -> tuple[int, int] | None:
    """Imports `payload` (an ExportPayload dict) into the website account
    matching these credentials. Returns (imported_tasks, imported_subtasks),
    or None if the credentials don't match or the site couldn't be reached.
    Never raises."""
    try:
        with httpx.Client(timeout=15) as client:
            session_cookie = _website_session_cookie(client, username, password)
            if not session_cookie:
                return None
            import_resp = client.post(
                f"{settings.public_base_url}/api/import?replace=true",
                json=payload,
                cookies={settings.cookie_name: session_cookie},
            )
            if import_resp.status_code != 200:
                return None
            body = import_resp.json()
            return body.get("imported_tasks", 0), body.get("imported_subtasks", 0)
    except httpx.HTTPError:
        return None


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest) -> dict:
    if not body.username.strip() or not body.password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username and password are required")
    if not crud.create_user(body.username, body.password):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    return {"username": body.username.strip()}


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response) -> UserResponse:
    username = body.username.strip()

    if crud.verify_user(username, body.password):
        set_session_cookie(response, username, is_guest=False, remember=body.remember_me)
        return UserResponse(username=username, is_guest=False)

    # First-time login with website credentials, from inside the desktop
    # app: bootstrap a matching local account and pull that account's data
    # in. Gated on the local username not already existing, so this only
    # ever fires once per account - an existing local account (even one
    # originally created this way) always just checks its own local
    # password on every later login, so reopening the app doesn't keep
    # re-importing duplicates of the same tasks. Later re-syncs are what the
    # explicit "Sync now" button (POST /sync below) is for.
    if is_desktop_build() and not crud.user_exists(username):
        tasks = _fetch_from_website(username, body.password)
        if tasks is not None:
            crud.create_user(username, body.password)
            crud.import_data(tasks, username)
            set_session_cookie(response, username, is_guest=False, remember=body.remember_me)
            return UserResponse(username=username, is_guest=False)

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")


@router.post("/sync", response_model=ImportResponse)
def sync_from_website(
    body: SyncRequest | None = None, current_user: CurrentUser = Depends(get_current_user)
) -> ImportResponse:
    if not is_desktop_build():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sync is only available in the desktop app")

    creds = _resolve_website_credentials(current_user, body)
    if creds is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No website account linked yet")
    username, password = creds

    tasks = _fetch_from_website(username, password)
    if tasks is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Those credentials don't match a website account")

    crud.set_website_link(current_user.username, username, password)
    # replace=True: Pull is a mirror/copy, not a merge - the local account
    # ends up holding exactly the website's tasks, nothing more. See
    # crud.import_data's docstring.
    imported_tasks, imported_subtasks = crud.import_data(tasks, current_user.username, replace=True)
    return ImportResponse(imported_tasks=imported_tasks, imported_subtasks=imported_subtasks)


@router.post("/push", response_model=ImportResponse)
def push_to_website(
    body: SyncRequest | None = None, current_user: CurrentUser = Depends(get_current_user)
) -> ImportResponse:
    if not is_desktop_build():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Push is only available in the desktop app")

    creds = _resolve_website_credentials(current_user, body)
    if creds is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No website account linked yet")
    username, password = creds

    tasks = crud.get_tasks_with_subtasks(current_user.username)
    payload = ExportPayload(exported_at=datetime.now().isoformat(), tasks=tasks).model_dump()

    result = _push_to_website(username, password, payload)
    if result is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Those credentials don't match a website account")

    crud.set_website_link(current_user.username, username, password)
    imported_tasks, imported_subtasks = result
    return ImportResponse(imported_tasks=imported_tasks, imported_subtasks=imported_subtasks)


@router.get("/website-link", response_model=WebsiteLinkResponse)
def website_link_status(current_user: CurrentUser = Depends(get_current_user)) -> WebsiteLinkResponse:
    if not is_desktop_build():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Only available in the desktop app")
    link = crud.get_website_link(current_user.username)
    if link is None:
        return WebsiteLinkResponse(linked=False)
    return WebsiteLinkResponse(linked=True, username=link["website_username"])


@router.post("/website-link/clear", status_code=status.HTTP_204_NO_CONTENT)
def unlink_website(current_user: CurrentUser = Depends(get_current_user)) -> None:
    if not is_desktop_build():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Only available in the desktop app")
    crud.clear_website_link(current_user.username)


@router.post("/guest", response_model=UserResponse)
def guest(response: Response) -> UserResponse:
    username = make_guest_username()
    set_session_cookie(response, username, is_guest=True)
    return UserResponse(username=username, is_guest=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    clear_session_cookie(response)


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse(username=current_user.username, is_guest=current_user.is_guest)


# ----------------------------- Google sign-in -----------------------------
# A full-page-redirect flow (not a fetch/XHR one, like the rest of this
# file) - OAuth fundamentally requires the browser itself to navigate to
# Google and back. The frontend just links straight to /google/login (see
# DownloadAppButton's sibling, the Google sign-in link in AuthPage) instead
# of calling it via the api client.


@router.get("/google/login")
def google_login() -> RedirectResponse:
    if not settings.google_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google sign-in isn't configured")

    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": f"{settings.public_base_url}/api/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    redirect = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    # Short-lived and not httponly-exempt from anything special - just a
    # CSRF check that whoever completes the callback is who we sent to
    # Google in the first place, not someone replaying/forging a callback.
    redirect.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return redirect


@router.get("/google/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    google_oauth_state: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE),
) -> RedirectResponse:
    if error or not code:
        return RedirectResponse(f"{settings.public_base_url}/?google_auth=failed")
    if not state or not google_oauth_state or not secrets.compare_digest(state, google_oauth_state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired sign-in attempt")

    redirect_uri = f"{settings.public_base_url}/api/auth/google/callback"
    with httpx.Client(timeout=10) as client:
        token_resp = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google sign-in failed")
        access_token = token_resp.json().get("access_token")

        userinfo_resp = client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        if userinfo_resp.status_code != 200:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google sign-in failed")
        userinfo = userinfo_resp.json()

    username = crud.get_or_create_google_user(google_sub=userinfo["sub"], email=userinfo.get("email"))

    redirect = RedirectResponse(f"{settings.public_base_url}/")
    set_session_cookie(redirect, username, is_guest=False)
    redirect.delete_cookie(OAUTH_STATE_COOKIE)
    return redirect
