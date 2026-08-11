import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from app import crud
from app.config import settings
from app.models import LoginRequest, SignupRequest, UserResponse
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


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest) -> dict:
    if not body.username.strip() or not body.password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username and password are required")
    if not crud.create_user(body.username, body.password):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    return {"username": body.username.strip()}


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response) -> UserResponse:
    if not crud.verify_user(body.username, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    username = body.username.strip()
    set_session_cookie(response, username, is_guest=False)
    return UserResponse(username=username, is_guest=False)


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
